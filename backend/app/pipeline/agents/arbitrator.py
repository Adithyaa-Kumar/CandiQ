"""
pipeline/agents/arbitrator.py
─────────────────────────────────
"""

from __future__ import annotations

import json

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
# Maximum the arbitrator can deviate from the weighted vote (Tier 4 fix)
MAX_ARBITRATOR_ADJUSTMENT = 15.0


class ArbitratorVerdict(BaseModel):
    candidate_id:    str
    consensus_score: float
    confidence:      float          # 0-100: specialist agreement signal
    strengths:       list[str]      # why they stand out — recruiter-ready
    risks:           list[str]      # specific concerns
    alternatives:    list[str]      # candidate_ids who could substitute


# ── Domain weight tables ──────────────────────────────────────────────────

def _domain_weights(domain: str) -> tuple[float, float, float]:
    """
    Returns (tech_w, trajectory_w, behavioral_w) summing to 1.0.
    These weights govern the pre-consensus vote — the arbitrator
    adjusts from this base, not from scratch.
    """
    WEIGHTS = {
        "machine_learning":     (0.55, 0.28, 0.17),
        "data_science":         (0.50, 0.30, 0.20),
        "data_engineering":     (0.50, 0.30, 0.20),
        "software_engineering": (0.45, 0.35, 0.20),
        "frontend":             (0.42, 0.32, 0.26),
        "mobile":               (0.42, 0.32, 0.26),
        "devops":               (0.38, 0.37, 0.25),
        "product":              (0.22, 0.48, 0.30),
        "design":               (0.28, 0.38, 0.34),
        "finance":              (0.28, 0.46, 0.26),
        "legal":                (0.18, 0.52, 0.30),
        "operations":           (0.22, 0.48, 0.30),
        "sales":                (0.18, 0.42, 0.40),
        "marketing":            (0.22, 0.38, 0.40),
        "hr":                   (0.18, 0.42, 0.40),
    }
    return WEIGHTS.get(domain, (0.40, 0.35, 0.25))


def _compute_weighted_vote(
    reviews: dict[str, AgentReviewResult],
    domain: str,
) -> float:
    """
    Domain-weighted pre-consensus score. This is the anchor — the
    arbitrator adjusts from here, bounded by MAX_ARBITRATOR_ADJUSTMENT.
    """
    tech_w, traj_w, behav_w = _domain_weights(domain)
    tech  = reviews.get("tech_specialist")
    traj  = reviews.get("trajectory_specialist")
    behav = reviews.get("behavioral_specialist")

    t_score  = (tech.score  if tech  else 50.0)
    tr_score = (traj.score  if traj  else 50.0)
    b_score  = (behav.score if behav else 50.0)

    return round(t_score * tech_w + tr_score * traj_w + b_score * behav_w, 2)


def _compute_confidence(reviews: dict[str, AgentReviewResult]) -> float:
    """
    Confidence based on specialist agreement (Tier 5).

    High agreement → high confidence: you can trust this score.
    Wide spread → low confidence: the three agents disagree — treat score with caution.

    Example:
      Tech=88, Traj=85, Behav=82 → spread=6  → confidence=93
      Tech=90, Traj=30, Behav=40 → spread=60 → confidence=28
    """
    scores = [r.score for r in reviews.values() if r is not None]
    if not scores:
        return 30.0
    if len(scores) == 1:
        return 50.0

    spread = max(scores) - min(scores)
    if spread <= 8:
        return 93.0
    elif spread <= 15:
        return 82.0
    elif spread <= 25:
        return 68.0
    elif spread <= 40:
        return 48.0
    elif spread <= 55:
        return 32.0
    else:
        return 20.0


_PROMPT_TEMPLATE = """\
You are the Lead Recruitment Arbitrator. Your role is NARROW and SPECIFIC:
1. Write recruiter-ready strengths (why this candidate stands out)
2. Write specific risks (what concerns a recruiter should know)
3. Suggest alternatives from the batch
4. Optionally ADJUST the pre-computed consensus score — but only within ±__MAX_ADJ__ points
   unless you have a hard disqualifying reason you can state explicitly.

CRITICAL RULE ON SCORING:
The pre-computed consensus score is a domain-weighted vote of three specialists.
You MUST NOT casually override it. The only valid reason to go outside ±__MAX_ADJ__ is:
  - A clear hard disqualifier the specialists missed (e.g., zero relevant experience in core domain)
  - State the reason explicitly in your risks list if you deviate beyond ±__MAX_ADJ__

JOB DESCRIPTION:
Role: __ROLE_TITLE__ (__SENIORITY__)
Domain: __DOMAIN__
Ideal: __IDEAL_SUMMARY__

SPECIALIST WEIGHT BREAKDOWN FOR THIS ROLE:
  Tech: __TECH_PCT__% | Trajectory: __TRAJ_PCT__% | Behavioral: __BEHAV_PCT__%

CANDIDATES AND THEIR PRE-COMPUTED SCORES:
__CANDIDATES_BLOCK__

ALL CANDIDATE IDs IN THIS BATCH (for alternatives field): __BATCH_IDS__

Respond ONLY with valid JSON, no markdown:
{
  "verdicts": [
    {
      "candidate_id": "<id>",
      "adjusted_score": <float — stay within pre_consensus ± __MAX_ADJ__ unless hard reason>,
      "strengths": ["<specific strength citing evidence>", "..."],
      "risks": ["<specific risk — concrete, not generic>", "..."],
      "alternatives": ["<candidate_id from batch only>", "..."]
    }
  ]
}

Include ALL __N__ candidates.\
"""


def _format_candidate_for_arbitrator(
    cid: str,
    name: str,
    reviews: dict[str, AgentReviewResult],
    pre_consensus: float,
    confidence: float,
    intel: dict,
) -> str:
    lines = [
        f"[{cid}] {name}",
        f"  Pre-consensus (weighted vote): {pre_consensus:.1f} | Confidence: {confidence:.0f}%",
    ]

    # Show pre-computed intelligence signals as grounding context
    why_sel = intel.get("why_selected", [])
    why_rej = intel.get("why_rejected", [])
    if why_sel:
        lines.append(f"  Evidence (strong): {' | '.join(why_sel[:3])}")
    if why_rej:
        lines.append(f"  Evidence (gaps): {' | '.join(why_rej[:2])}")

    for agent_key, label in (
        ("tech_specialist",       "Tech"),
        ("trajectory_specialist", "Trajectory"),
        ("behavioral_specialist", "Behavioral"),
    ):
        r = reviews.get(agent_key)
        if r:
            lines.append(
                f"  {label}: {r.score:.0f}/100 — "
                f"pros: {r.pros[:2]} | cons: {r.cons[:2]} | {(r.rationale or '')[:150]}"
            )

    return "\n".join(lines)


def _build_prompt(
    jd_signals: JDSignals,
    batch: list[tuple[str, str, dict[str, AgentReviewResult], float, float, dict]],
) -> str:
    tech_w, traj_w, behav_w = _domain_weights(jd_signals.domain)
    batch_ids = [cid for cid, *_ in batch]

    candidates_block = "\n\n".join(
        _format_candidate_for_arbitrator(cid, name, reviews, pre, conf, intel)
        for cid, name, reviews, pre, conf, intel in batch
    )

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__",   jd_signals.role_title)
    prompt = prompt.replace("__SENIORITY__",     jd_signals.seniority)
    prompt = prompt.replace("__DOMAIN__",        jd_signals.domain)
    prompt = prompt.replace("__IDEAL_SUMMARY__", jd_signals.ideal_candidate_summary[:400])
    prompt = prompt.replace("__TECH_PCT__",      str(int(tech_w  * 100)))
    prompt = prompt.replace("__TRAJ_PCT__",      str(int(traj_w  * 100)))
    prompt = prompt.replace("__BEHAV_PCT__",     str(int(behav_w * 100)))
    prompt = prompt.replace("__BATCH_IDS__",     ", ".join(batch_ids))
    prompt = prompt.replace("__CANDIDATES_BLOCK__", candidates_block)
    prompt = prompt.replace("__MAX_ADJ__",       str(int(MAX_ARBITRATOR_ADJUSTMENT)))
    prompt = prompt.replace("__N__",             str(len(batch)))
    return prompt


def _clamp_to_weighted_vote(
    arbitrator_score: float,
    pre_consensus: float,
    hard_reason: bool = False,
) -> float:
    """
    Clamp the arbitrator's proposed score to ±MAX_ARBITRATOR_ADJUSTMENT
    of the weighted vote. If a hard reason was flagged, allow full range.
    """
    if hard_reason:
        return round(max(0.0, min(100.0, arbitrator_score)), 2)

    lo = pre_consensus - MAX_ARBITRATOR_ADJUSTMENT
    hi = pre_consensus + MAX_ARBITRATOR_ADJUSTMENT
    return round(max(lo, min(hi, arbitrator_score)), 2)


def _fallback_verdict(
    candidate_id: str,
    reviews: dict[str, AgentReviewResult],
    intel: dict,
    domain: str,
    pre_consensus: float,
    confidence: float,
) -> ArbitratorVerdict:
    return ArbitratorVerdict(
        candidate_id=candidate_id,
        consensus_score=pre_consensus,   # fall back to the weighted vote exactly
        confidence=confidence,
        strengths=intel.get("why_selected", ["Automated consensus — arbitrator unavailable"]),
        risks=intel.get("why_rejected", ["Score is weighted specialist average; treat with caution"]),
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

    # Pre-compute weighted votes and confidence for every candidate
    enriched = []
    for cid, name, reviews in candidate_reviews:
        pre_consensus = _compute_weighted_vote(reviews, jd_signals.domain)
        confidence    = _compute_confidence(reviews)
        intel         = intel_map.get(cid, {})
        enriched.append((cid, name, reviews, pre_consensus, confidence, intel))

    batches = [
        enriched[i : i + ARBITRATOR_BATCH_SIZE]
        for i in range(0, len(enriched), ARBITRATOR_BATCH_SIZE)
    ]

    for batch in batches:
        prompt       = _build_prompt(jd_signals, batch)
        expected_ids = [cid for cid, *_ in batch]
        pre_map      = {cid: pre for cid, _, _, pre, _, _ in batch}
        conf_map     = {cid: conf for cid, _, _, _, conf, _ in batch}

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

                pre_consensus = pre_map[cid]
                confidence    = conf_map[cid]

                arb_score = float(item.get("adjusted_score", pre_consensus))
                risks     = [str(r) for r in item.get("risks", [])]

                # A hard reason must be explicit in risks to justify going outside the band
                hard_reason = any(
                    kw in " ".join(risks).lower()
                    for kw in ("zero experience", "no relevant", "completely unrelated",
                               "hard disqualif", "wrong domain", "no evidence")
                )

                final_score = _clamp_to_weighted_vote(arb_score, pre_consensus, hard_reason)

                # Safe alternatives: only IDs from this batch, not the candidate itself
                safe_alts = [
                    str(a) for a in item.get("alternatives", [])
                    if str(a) in expected_ids and str(a) != cid
                ]

                # Merge intelligence signals with arbitrator output
                intel     = next((i for c, _, _, _, _, i in batch if c == cid), {})
                arb_str   = [str(s) for s in item.get("strengths", [])]
                arb_risk  = risks

                merged_strengths = list(dict.fromkeys(intel.get("why_selected", []) + arb_str))[:5]
                merged_risks     = list(dict.fromkeys(intel.get("why_rejected", []) + arb_risk))[:4]

                batch_results[cid] = ArbitratorVerdict(
                    candidate_id=cid,
                    consensus_score=final_score,
                    confidence=confidence,
                    strengths=merged_strengths,
                    risks=merged_risks,
                    alternatives=safe_alts,
                )

            for cid, name, reviews, pre, conf, intel in batch:
                if cid not in batch_results:
                    batch_results[cid] = _fallback_verdict(
                        cid, reviews, intel, jd_signals.domain, pre, conf
                    )

            results.update(batch_results)

        except Exception as e:
            logger.error("arbitrator_batch_failed", error=str(e), batch_size=len(batch))
            for cid, name, reviews, pre, conf, intel in batch:
                results[cid] = _fallback_verdict(
                    cid, reviews, intel, jd_signals.domain, pre, conf
                )

    return results