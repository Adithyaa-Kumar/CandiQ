"""
pipeline/agents/arbitrator.py
─────────────────────────────────
Final Arbitrator Agent.

Takes the 3 specialist reviews for each shortlisted candidate, resolves
disagreements, weighs them against the JD, and produces the definitive
consensus score + executive summary that recruiters see.

BUG FIXES applied:
  1. The arbitrator prompt said "Do NOT simply average the three scores"
     but gave no guidance on how to weight disagreements — in practice
     the model averaged anyway. Added explicit weighting guidance tied to
     the role domain: technical roles → tech_specialist score weighs more;
     leadership roles → trajectory score weighs more.
  2. `alternatives` field was intended to hold candidate_ids of backup
     candidates from the SAME BATCH — but the arbitrator prompt gave no
     indication which batch it was operating on, so the model would
     hallucinate IDs from outside the batch. Now the prompt lists all
     candidate IDs up front so the model can only reference real ones.
  3. Fallback verdict used simple average — improved to use weighted
     average based on domain weights (tech domain → tech score weighs 50%).
  4. Batch size was 8 but each candidate's review block averages ~300 chars
     × 3 agents = ~900 chars per candidate — 8 candidates = ~7.2k chars
     just for reviews, plus the system prompt. Kept at 8 but added
     truncation for very long rationale strings (>200 chars per agent).
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

import google.generativeai as genai

from app.pipeline.agents.base import AgentReviewResult, _call_llm, _strip_fences
from app.pipeline.jd_analyzer import JDSignals
from app.config import get_settings
from app.logging_conf import get_logger

logger = get_logger(__name__)

_settings = get_settings()
_ARBITRATOR_MODEL = genai.GenerativeModel(_settings.gemini_arbitrator_model)

ARBITRATOR_BATCH_SIZE = 8


class ArbitratorVerdict(BaseModel):
    candidate_id: str
    consensus_score: float
    strengths: list[str]
    risks: list[str]
    alternatives: list[str]


def _tech_weight(domain: str) -> tuple[float, float, float]:
    """Returns (tech_w, trajectory_w, behavioral_w) per domain."""
    DOMAIN_WEIGHTS = {
        "machine_learning":   (0.55, 0.30, 0.15),
        "data_science":       (0.50, 0.30, 0.20),
        "data_engineering":   (0.50, 0.30, 0.20),
        "software_engineering": (0.45, 0.35, 0.20),
        "frontend":           (0.45, 0.30, 0.25),
        "mobile":             (0.45, 0.30, 0.25),
        "devops":             (0.40, 0.35, 0.25),
        "product":            (0.25, 0.45, 0.30),
        "design":             (0.30, 0.35, 0.35),
        "finance":            (0.30, 0.45, 0.25),
        "legal":              (0.20, 0.50, 0.30),
        "operations":         (0.25, 0.45, 0.30),
        "sales":              (0.20, 0.40, 0.40),
        "marketing":          (0.25, 0.35, 0.40),
        "hr":                 (0.20, 0.40, 0.40),
    }
    return DOMAIN_WEIGHTS.get(domain, (0.40, 0.35, 0.25))


_PROMPT_TEMPLATE = """\
You are the Lead Recruitment Arbitrator. You have three specialist panel
reviews for each candidate below. Produce a final verdict for each.

JOB DESCRIPTION CONTEXT:
Role: __ROLE_TITLE__ (__SENIORITY__)
Domain: __DOMAIN__
Ideal candidate: __IDEAL_SUMMARY__

SCORE WEIGHTING FOR THIS ROLE (use these weights when reconciling):
  Tech Specialist:        __TECH_W_PCT__%
  Trajectory Specialist:  __TRAJ_W_PCT__%
  Behavioral Specialist:  __BEHAV_W_PCT__%

CANDIDATES IN THIS BATCH: __BATCH_IDS__

RULES:
1. Start from the weighted average but DEVIATE when one specialist flags
   a hard disqualifying gap (e.g. zero relevant stack experience for a
   technical role, or serial job-hopping for a seniority-critical role).
   A single critical failing should pull the score down significantly —
   a mediocre tech score (30) with strong trajectory (90) and behavioral
   (80) should NOT yield 67 for a technical role; tech is weighted 55%.
2. Keep consensus_score within the range [min(three scores) - 10,
   max(three scores) + 10] unless there's a clear reason to go outside.
3. strengths: 2-4 recruiter-ready bullet points on why this candidate
   stands out. Be specific — "strong embedding experience" is better
   than "good ML background".
4. risks: 1-3 specific concerns a hiring manager should probe. Concrete,
   not generic ("only 2yr tenure at current role" not "may not be committed").
5. alternatives: candidate_ids from BATCH_IDS above who could substitute
   if this candidate declines. Leave [] if none. ONLY use IDs from BATCH_IDS.

PANEL REVIEWS:
__CANDIDATES_BLOCK__

Respond ONLY with valid JSON, no markdown fences:
{
  "verdicts": [
    {
      "candidate_id": "<id>",
      "consensus_score": <0-100 float>,
      "strengths": ["<short phrase>", "..."],
      "risks": ["<short phrase>", "..."],
      "alternatives": ["<candidate_id from batch>", "..."]
    }
  ]
}

Include ALL __N__ candidates.\
"""


def _format_candidate_reviews(
    candidate_id: str,
    candidate_name: str,
    reviews: dict[str, AgentReviewResult],
) -> str:
    lines = [f"[{candidate_id}] {candidate_name}"]
    for agent_key, label in (
        ("tech_specialist",       "Tech Specialist"),
        ("trajectory_specialist", "Trajectory Specialist"),
        ("behavioral_specialist", "Behavioral Specialist"),
    ):
        r = reviews.get(agent_key)
        if r:
            # FIX 4: truncate long rationales to keep prompt size bounded
            rationale = r.rationale[:200] if r.rationale else ""
            lines.append(
                f"  {label}: score={r.score:.0f} | "
                f"pros={r.pros[:3]} | cons={r.cons[:3]} | {rationale}"
            )
    return "\n".join(lines)


def _build_prompt(
    jd_signals: JDSignals,
    batch: list[tuple[str, str, dict[str, AgentReviewResult]]],
) -> str:
    tech_w, traj_w, behav_w = _tech_weight(jd_signals.domain)
    batch_ids = [cid for cid, _, _ in batch]

    candidates_block = "\n\n".join(
        _format_candidate_reviews(cid, name, reviews) for cid, name, reviews in batch
    )

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__",    jd_signals.role_title)
    prompt = prompt.replace("__SENIORITY__",      jd_signals.seniority)
    prompt = prompt.replace("__DOMAIN__",         jd_signals.domain)
    prompt = prompt.replace("__IDEAL_SUMMARY__",  jd_signals.ideal_candidate_summary[:400])
    # FIX 1: explicit weights in the prompt
    prompt = prompt.replace("__TECH_W_PCT__",     str(int(tech_w  * 100)))
    prompt = prompt.replace("__TRAJ_W_PCT__",     str(int(traj_w  * 100)))
    prompt = prompt.replace("__BEHAV_W_PCT__",    str(int(behav_w * 100)))
    # FIX 2: list all batch IDs so model only references real ones
    prompt = prompt.replace("__BATCH_IDS__",      ", ".join(batch_ids))
    prompt = prompt.replace("__CANDIDATES_BLOCK__", candidates_block)
    prompt = prompt.replace("__N__",              str(len(batch)))
    return prompt


def _fallback_verdict(
    candidate_id: str,
    reviews: dict[str, AgentReviewResult],
    domain: str = "other",
) -> ArbitratorVerdict:
    """FIX 3: weighted fallback instead of simple average."""
    tech_w, traj_w, behav_w = _tech_weight(domain)
    tech  = reviews.get("tech_specialist")
    traj  = reviews.get("trajectory_specialist")
    behav = reviews.get("behavioral_specialist")

    if tech or traj or behav:
        t_s = (tech.score  if tech  else 50.0) * tech_w
        tr_s= (traj.score  if traj  else 50.0) * traj_w
        b_s = (behav.score if behav else 50.0) * behav_w
        score = round(t_s + tr_s + b_s, 2)
    else:
        score = 50.0

    return ArbitratorVerdict(
        candidate_id=candidate_id,
        consensus_score=score,
        strengths=["Automated consensus — arbitrator unavailable"],
        risks=["Scores are a weighted average of panel; treat with lower confidence"],
        alternatives=[],
    )


def run_arbitrator(
    jd_signals: JDSignals,
    candidate_reviews: list[tuple[str, str, dict[str, AgentReviewResult]]],
) -> dict[str, ArbitratorVerdict]:
    if not candidate_reviews:
        return {}

    results: dict[str, ArbitratorVerdict] = {}
    batches = [
        candidate_reviews[i : i + ARBITRATOR_BATCH_SIZE]
        for i in range(0, len(candidate_reviews), ARBITRATOR_BATCH_SIZE)
    ]

    for batch in batches:
        prompt = _build_prompt(jd_signals, batch)
        expected_ids = [cid for cid, _, _ in batch]

        try:
            raw = _call_llm(prompt, max_tokens=4096, model=_ARBITRATOR_MODEL)
            cleaned = _strip_fences(raw)
            data = json.loads(cleaned)
            verdicts = data.get("verdicts", [])

            batch_results: dict[str, ArbitratorVerdict] = {}
            for item in verdicts:
                cid = str(item.get("candidate_id", ""))
                if cid not in expected_ids:
                    continue
                # FIX 2: only keep alternatives that are real batch IDs
                safe_alts = [
                    str(a) for a in item.get("alternatives", [])
                    if str(a) in expected_ids and str(a) != cid
                ]
                batch_results[cid] = ArbitratorVerdict(
                    candidate_id=cid,
                    consensus_score=float(item.get("consensus_score", 50.0)),
                    strengths=[str(s) for s in item.get("strengths", [])],
                    risks=[str(r) for r in item.get("risks", [])],
                    alternatives=safe_alts,
                )

            for cid, name, reviews in batch:
                if cid not in batch_results:
                    batch_results[cid] = _fallback_verdict(cid, reviews, jd_signals.domain)

            results.update(batch_results)

        except Exception as e:
            logger.error("arbitrator_batch_failed", error=str(e), batch_size=len(batch))
            for cid, name, reviews in batch:
                results[cid] = _fallback_verdict(cid, reviews, jd_signals.domain)

    return results