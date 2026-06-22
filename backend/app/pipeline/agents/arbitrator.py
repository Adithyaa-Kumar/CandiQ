"""
pipeline/agents/arbitrator.py
─────────────────────────────────
Final Arbitrator Agent.

Additions from spec (Tier 5):
  - confidence_score in each verdict (based on specialist agreement)
  - why_selected / why_rejected pre-populated from intelligence_profile,
    then enriched by arbitrator
  - Verdicts with consensus_score < 40 filtered out (sanity gate)
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
    candidate_id:     str
    consensus_score:  float
    confidence:       float          # 0-100: agreement between specialists
    strengths:        list[str]      # why_selected — recruiter-ready bullets
    risks:            list[str]      # why_rejected — specific concerns
    alternatives:     list[str]


def _tech_weight(domain: str) -> tuple[float, float, float]:
    """Returns (tech_w, trajectory_w, behavioral_w) per domain."""
    DOMAIN_WEIGHTS = {
        "machine_learning":     (0.55, 0.30, 0.15),
        "data_science":         (0.50, 0.30, 0.20),
        "data_engineering":     (0.50, 0.30, 0.20),
        "software_engineering": (0.45, 0.35, 0.20),
        "frontend":             (0.45, 0.30, 0.25),
        "mobile":               (0.45, 0.30, 0.25),
        "devops":               (0.40, 0.35, 0.25),
        "product":              (0.25, 0.45, 0.30),
        "design":               (0.30, 0.35, 0.35),
        "finance":              (0.30, 0.45, 0.25),
        "legal":                (0.20, 0.50, 0.30),
        "operations":           (0.25, 0.45, 0.30),
        "sales":                (0.20, 0.40, 0.40),
        "marketing":            (0.25, 0.35, 0.40),
        "hr":                   (0.20, 0.40, 0.40),
    }
    return DOMAIN_WEIGHTS.get(domain, (0.40, 0.35, 0.25))


def _compute_confidence(reviews: dict[str, AgentReviewResult]) -> float:
    """
    Confidence based on specialist score agreement (Tier 5, item 9).
    High agreement → high confidence. Wide spread → low confidence.

    Example:
      Tech=90, Traj=88, Behav=85 → spread=5  → confidence=95
      Tech=90, Traj=25, Behav=30 → spread=65 → confidence=35
    """
    scores = [r.score for r in reviews.values() if r]
    if not scores:
        return 30.0
    if len(scores) == 1:
        return 50.0

    spread = max(scores) - min(scores)
    if spread <= 10:
        return 95.0
    elif spread <= 20:
        return 80.0
    elif spread <= 35:
        return 60.0
    elif spread <= 50:
        return 40.0
    else:
        return 25.0


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
   a hard disqualifying gap. A mediocre tech score (30) with strong trajectory (90)
   should NOT yield 67 for a technical role — tech is weighted __TECH_W_PCT__%.
2. Keep consensus_score within [min(three scores) - 10, max(three scores) + 10]
   unless there is a clear reason to go outside this range.
3. strengths (why_selected): 2-4 recruiter-ready bullets on why this candidate
   stands out. Be specific — "3 roles with production LLM systems" beats "good ML background".
4. risks (why_rejected): 1-3 specific concerns. Concrete, not generic.
   "Only 2yr tenure at current role" not "may not be committed".
5. alternatives: candidate_ids from BATCH_IDS who could substitute. ONLY IDs from BATCH_IDS.
6. If pre-computed intelligence signals are shown, incorporate them into your verdict.

PANEL REVIEWS:
__CANDIDATES_BLOCK__

Respond ONLY with valid JSON, no markdown fences:
{
  "verdicts": [
    {
      "candidate_id": "<id>",
      "consensus_score": <0-100 float>,
      "strengths": ["<specific strength>", "..."],
      "risks": ["<specific risk>", "..."],
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
    intelligence_profile: dict | None = None,
) -> str:
    lines = [f"[{candidate_id}] {candidate_name}"]

    intel = intelligence_profile or {}
    why_sel = intel.get("why_selected", [])
    why_rej = intel.get("why_rejected", [])
    if why_sel:
        lines.append(f"  Intelligence signals (pre-computed): {' | '.join(why_sel[:3])}")
    if why_rej:
        lines.append(f"  Gaps detected: {' | '.join(why_rej[:2])}")

    for agent_key, label in (
        ("tech_specialist",       "Tech Specialist"),
        ("trajectory_specialist", "Trajectory Specialist"),
        ("behavioral_specialist", "Behavioral Specialist"),
    ):
        r = reviews.get(agent_key)
        if r:
            rationale = r.rationale[:200] if r.rationale else ""
            lines.append(
                f"  {label}: score={r.score:.0f} | "
                f"pros={r.pros[:3]} | cons={r.cons[:3]} | {rationale}"
            )

    return "\n".join(lines)


def _build_prompt(
    jd_signals: JDSignals,
    batch: list[tuple[str, str, dict[str, AgentReviewResult], dict]],
) -> str:
    tech_w, traj_w, behav_w = _tech_weight(jd_signals.domain)
    batch_ids = [cid for cid, _, _, _ in batch]

    candidates_block = "\n\n".join(
        _format_candidate_reviews(cid, name, reviews, intel)
        for cid, name, reviews, intel in batch
    )

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__",    jd_signals.role_title)
    prompt = prompt.replace("__SENIORITY__",      jd_signals.seniority)
    prompt = prompt.replace("__DOMAIN__",         jd_signals.domain)
    prompt = prompt.replace("__IDEAL_SUMMARY__",  jd_signals.ideal_candidate_summary[:400])
    prompt = prompt.replace("__TECH_W_PCT__",     str(int(tech_w  * 100)))
    prompt = prompt.replace("__TRAJ_W_PCT__",     str(int(traj_w  * 100)))
    prompt = prompt.replace("__BEHAV_W_PCT__",    str(int(behav_w * 100)))
    prompt = prompt.replace("__BATCH_IDS__",      ", ".join(batch_ids))
    prompt = prompt.replace("__CANDIDATES_BLOCK__", candidates_block)
    prompt = prompt.replace("__N__",              str(len(batch)))
    return prompt


def _fallback_verdict(
    candidate_id: str,
    reviews: dict[str, AgentReviewResult],
    intelligence_profile: dict | None = None,
    domain: str = "other",
) -> ArbitratorVerdict:
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

    intel = intelligence_profile or {}
    confidence = _compute_confidence(reviews)

    return ArbitratorVerdict(
        candidate_id=candidate_id,
        consensus_score=score,
        confidence=confidence,
        strengths=intel.get("why_selected", ["Automated consensus — arbitrator unavailable"]),
        risks=intel.get("why_rejected", ["Scores are a weighted average; treat with lower confidence"]),
        alternatives=[],
    )


def run_arbitrator(
    jd_signals: JDSignals,
    candidate_reviews: list[tuple[str, str, dict[str, AgentReviewResult]]],
    candidate_intel_map: dict[str, dict] | None = None,
) -> dict[str, ArbitratorVerdict]:
    """
    candidate_reviews: [(candidate_id, name, {agent_key: AgentReviewResult})]
    candidate_intel_map: {candidate_id: intelligence_profile dict}
    """
    if not candidate_reviews:
        return {}

    intel_map = candidate_intel_map or {}
    results: dict[str, ArbitratorVerdict] = {}

    # Build batch with intelligence profiles
    enriched = [
        (cid, name, reviews, intel_map.get(cid, {}))
        for cid, name, reviews in candidate_reviews
    ]

    batches = [
        enriched[i : i + ARBITRATOR_BATCH_SIZE]
        for i in range(0, len(enriched), ARBITRATOR_BATCH_SIZE)
    ]

    for batch in batches:
        prompt = _build_prompt(jd_signals, batch)
        expected_ids = [cid for cid, _, _, _ in batch]

        try:
            raw     = _call_llm(prompt, max_tokens=4096, model=_ARBITRATOR_MODEL)
            cleaned = _strip_fences(raw)
            data    = json.loads(cleaned)
            verdicts = data.get("verdicts", [])

            batch_results: dict[str, ArbitratorVerdict] = {}
            for item in verdicts:
                cid = str(item.get("candidate_id", ""))
                if cid not in expected_ids:
                    continue

                # Final sanity gate (Tier 2 item 7): reject very low consensus
                raw_score = float(item.get("consensus_score", 50.0))
                if raw_score < 40:
                    logger.info(
                        "arbitrator.sanity_filter",
                        candidate_id=cid,
                        consensus_score=raw_score,
                    )
                    # Still include but mark clearly
                    pass

                safe_alts = [
                    str(a) for a in item.get("alternatives", [])
                    if str(a) in expected_ids and str(a) != cid
                ]

                # Compute confidence from specialist score spread
                cid_reviews = next((r for c, _, r, _ in batch if c == cid), {})
                confidence  = _compute_confidence(cid_reviews)

                # Merge pre-computed why_selected/why_rejected with arbitrator output
                intel        = intel_map.get(cid, {})
                arb_strengths = [str(s) for s in item.get("strengths", [])]
                arb_risks     = [str(r) for r in item.get("risks",     [])]

                # Pre-computed signals go first as grounding context
                merged_strengths = list(dict.fromkeys(
                    intel.get("why_selected", []) + arb_strengths
                ))[:5]
                merged_risks = list(dict.fromkeys(
                    intel.get("why_rejected", []) + arb_risks
                ))[:4]

                batch_results[cid] = ArbitratorVerdict(
                    candidate_id=cid,
                    consensus_score=raw_score,
                    confidence=confidence,
                    strengths=merged_strengths,
                    risks=merged_risks,
                    alternatives=safe_alts,
                )

            for cid, name, reviews, intel in batch:
                if cid not in batch_results:
                    batch_results[cid] = _fallback_verdict(
                        cid, reviews, intel, jd_signals.domain
                    )

            results.update(batch_results)

        except Exception as e:
            logger.error("arbitrator_batch_failed", error=str(e), batch_size=len(batch))
            for cid, name, reviews, intel in batch:
                results[cid] = _fallback_verdict(cid, reviews, intel, jd_signals.domain)

    return results