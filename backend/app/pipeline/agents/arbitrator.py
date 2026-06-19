"""
pipeline/agents/arbitrator.py
─────────────────────────────────
Final Arbitrator Agent.

Takes the 3 specialist reviews for each shortlisted candidate, resolves
disagreements, weighs them against the JD, and produces the definitive
consensus score + executive summary that recruiters see.

Batched at ARBITRATOR_BATCH_SIZE candidates per call (not 1-per-call)
to keep total API calls bounded — the arbitrator's job (reconcile 3
existing scores + write a summary) doesn't need full prompt isolation
per candidate the way the specialist passes do.
"""

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
# Arbitrator runs far fewer calls than specialists (~batches of 8 vs full shortlist),
# so we can afford the stronger model here — this is the highest-judgment step.
_ARBITRATOR_MODEL = genai.GenerativeModel(_settings.gemini_arbitrator_model)

ARBITRATOR_BATCH_SIZE = 8


class ArbitratorVerdict(BaseModel):
    candidate_id: str
    consensus_score: float
    strengths: list[str]
    risks: list[str]
    alternatives: list[str]   # other candidates worth considering if this one is unavailable


_PROMPT_TEMPLATE = """You are the Lead Recruitment Arbitrator. You have three specialist panel
reviews for each candidate below. Your job is to resolve any conflicts between their
scores, weigh their pros/cons against the actual job description, and deliver a final
verdict for each candidate.

JOB DESCRIPTION CONTEXT:
Role: __ROLE_TITLE__ (__SENIORITY__)
Ideal candidate: __IDEAL_SUMMARY__

For each candidate, you are given:
  - Tech Specialist score + pros/cons/rationale
  - Trajectory Specialist score + pros/cons/rationale
  - Behavioral Specialist score + pros/cons/rationale

Your job:
1. Do NOT simply average the three scores. Use judgement — if the Tech Specialist
   flags a hard disqualifying gap (e.g. zero relevant stack experience), that should
   weigh more heavily than a strong trajectory score for a highly technical role.
2. Produce three short lists:
   - strengths: 2-4 bullets on why this candidate stands out (recruiter-facing, specific)
   - risks: 1-3 bullets on genuine concerns or gaps a hiring manager should probe
   - alternatives: candidate_ids of other candidates in this batch who could substitute
     if this candidate declines or falls through (leave empty [] if none)

CANDIDATES AND PANEL REVIEWS:
__CANDIDATES_BLOCK__

Respond ONLY with valid JSON, no markdown fences:
{
  "verdicts": [
    {
      "candidate_id": "<id>",
      "consensus_score": <0-100>,
      "strengths": ["<short phrase>", "..."],
      "risks": ["<short phrase>", "..."],
      "alternatives": ["<candidate_id>", "..."]
    }
  ]
}

Include ALL __N__ candidates."""


def _format_candidate_reviews(
    candidate_id: str,
    candidate_name: str,
    reviews: dict[str, AgentReviewResult],
) -> str:
    lines = [f"[{candidate_id}] {candidate_name}"]
    for agent_key, label in (
        ("tech_specialist", "Tech Specialist"),
        ("trajectory_specialist", "Trajectory Specialist"),
        ("behavioral_specialist", "Behavioral Specialist"),
    ):
        r = reviews.get(agent_key)
        if r:
            lines.append(
                f"  {label}: score={r.score} | pros={r.pros} | cons={r.cons} | {r.rationale}"
            )
    return "\n".join(lines)


def _build_prompt(
    jd_signals: JDSignals,
    batch: list[tuple[str, str, dict[str, AgentReviewResult]]],
) -> str:
    candidates_block = "\n\n".join(
        _format_candidate_reviews(cid, name, reviews) for cid, name, reviews in batch
    )

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__", jd_signals.role_title)
    prompt = prompt.replace("__SENIORITY__", jd_signals.seniority)
    prompt = prompt.replace("__IDEAL_SUMMARY__", jd_signals.ideal_candidate_summary[:600])
    prompt = prompt.replace("__CANDIDATES_BLOCK__", candidates_block)
    prompt = prompt.replace("__N__", str(len(batch)))
    return prompt


def _fallback_verdict(candidate_id: str, reviews: dict[str, AgentReviewResult]) -> ArbitratorVerdict:
    """Simple average fallback if the arbitrator call fails for this batch."""
    scores = [r.score for r in reviews.values()] or [50.0]
    return ArbitratorVerdict(
        candidate_id=candidate_id,
        consensus_score=round(sum(scores) / len(scores), 2),
        strengths=["Automated consensus — arbitrator unavailable"],
        risks=["Scores are a simple average of panel; treat with lower confidence"],
        alternatives=[],
    )


def run_arbitrator(
    jd_signals: JDSignals,
    candidate_reviews: list[tuple[str, str, dict[str, AgentReviewResult]]],
) -> dict[str, ArbitratorVerdict]:
    """
    candidate_reviews: list of (candidate_id, candidate_name, {agent_key: AgentReviewResult})
    Returns {candidate_id: ArbitratorVerdict}
    """
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
                batch_results[cid] = ArbitratorVerdict(
                    candidate_id=cid,
                    consensus_score=float(item.get("consensus_score", 50.0)),
                    strengths=[str(s) for s in item.get("strengths", [])],
                    risks=[str(r) for r in item.get("risks", [])],
                    alternatives=[str(a) for a in item.get("alternatives", [])],
                )

            for cid, name, reviews in batch:
                if cid not in batch_results:
                    batch_results[cid] = _fallback_verdict(cid, reviews)

            results.update(batch_results)

        except Exception as e:
            logger.error("arbitrator_batch_failed", error=str(e), batch_size=len(batch))
            for cid, name, reviews in batch:
                results[cid] = _fallback_verdict(cid, reviews)

    return results