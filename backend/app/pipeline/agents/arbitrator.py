"""
pipeline/agents/arbitrator.py
───────────────────────────────
Final Arbitrator — weighted consensus with hard domain enforcement.

KEY ARCHITECTURAL FIXES
────────────────────────
1. Arbitrator can only adjust ±12 from the weighted-vote pre-consensus.
   This prevents it from "rescuing" a 5-point tech candidate to 40.

2. Domain-weighted votes: ML roles weight tech at 55%, trajectory 28%, behavioral 17%.
   A graphic designer who got tech=5, traj=10, behav=10 gets pre-consensus = 7.6.
   The arbitrator can only produce 7.6 ± 12 = max 19.6.
   This candidate correctly appears near the bottom of results.

3. Confidence scoring: wide specialist spread → low confidence.
   Tech=88, Traj=85, Behav=82 (spread=6) → 93% confidence.
   Tech=5, Traj=10, Behav=10 (spread=5) → 93% confidence but score=7.6.

4. The arbitrator's JOB is now: write strengths/risks/alternatives.
   Not: override the score. The score comes from the weighted vote.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

import google.generativeai as genai

from app.pipeline.agents.base import AgentReviewResult, _call_llm, _strip_fences
from app.pipeline.jd_analyzer import JDSignals
from app.config import get_settings
from app.logging_conf import get_logger

logger = get_logger(__name__)

_settings = get_settings()
_ARBITRATOR_MODEL = genai.GenerativeModel(_settings.gemini_arbitrator_model)

ARBITRATOR_BATCH_SIZE = 8
MAX_ARBITRATOR_ADJUSTMENT = 12.0  # Tightened from 15 to prevent inflation


class ArbitratorVerdict(BaseModel):
    candidate_id:    str
    consensus_score: float
    confidence:      float
    strengths:       list[str]
    risks:           list[str]
    alternatives:    list[str]


def _domain_weights(domain: str) -> tuple[float, float, float]:
    """tech_w, trajectory_w, behavioral_w — sum to 1.0."""
    WEIGHTS = {
        "machine_learning":     (0.55, 0.28, 0.17),
        "data_science":         (0.50, 0.30, 0.20),
        "data_engineering":     (0.50, 0.30, 0.20),
        "software_engineering": (0.45, 0.35, 0.20),
        "frontend":             (0.40, 0.33, 0.27),
        "mobile":               (0.40, 0.33, 0.27),
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


def _compute_weighted_vote(reviews: dict[str, AgentReviewResult], domain: str) -> float:
    tech_w, traj_w, behav_w = _domain_weights(domain)
    t  = reviews.get("tech_specialist")
    tr = reviews.get("trajectory_specialist")
    b  = reviews.get("behavioral_specialist")
    return round(
        (t.score  if t  else 50.0) * tech_w +
        (tr.score if tr else 50.0) * traj_w +
        (b.score  if b  else 50.0) * behav_w,
        2,
    )


def _compute_confidence(reviews: dict[str, AgentReviewResult]) -> float:
    scores = [r.score for r in reviews.values() if r is not None]
    if not scores: return 30.0
    if len(scores) == 1: return 50.0
    spread = max(scores) - min(scores)
    if spread <= 8:  return 93.0
    if spread <= 15: return 82.0
    if spread <= 25: return 68.0
    if spread <= 40: return 48.0
    if spread <= 55: return 32.0
    return 20.0


_PROMPT_TEMPLATE = """\
You are the Lead Recruitment Arbitrator. Your job is NARROW:
1. Write recruiter-facing strengths (what makes this candidate stand out for THIS role)
2. Write specific, concrete risks (not generic)
3. Suggest alternative candidates from this batch who could substitute

SCORING RULE — READ AND FOLLOW:
The pre-computed consensus is a domain-weighted specialist vote. Your adjusted_score
MUST stay within pre_consensus ± __MAX_ADJ__ UNLESS you can state a hard factual reason
in the risks list. You CANNOT rescue a low-scoring candidate with a high adjusted_score.
If tech=5, traj=10, behav=10, pre_consensus=7.6 — your score must be 0–19.6 MAX.

JOB: __ROLE_TITLE__ (__SENIORITY__) | Domain: __DOMAIN__
Ideal candidate: __IDEAL_SUMMARY__

Specialist weight breakdown: Tech __TECH_PCT__% | Trajectory __TRAJ_PCT__% | Behavioral __BEHAV_PCT__%

CANDIDATES:
__CANDIDATES_BLOCK__

ALL IDs IN THIS BATCH (use for alternatives): __BATCH_IDS__

Respond ONLY with valid JSON, no markdown:
{
  "verdicts": [
    {
      "candidate_id": "<id>",
      "adjusted_score": <float within pre_consensus ± __MAX_ADJ__>,
      "strengths": ["<specific strength citing career evidence>"],
      "risks": ["<specific concrete risk — not generic>"],
      "alternatives": ["<id from batch>"]
    }
  ]
}

Include ALL __N__ candidates.\
"""


def _format_candidate(
    cid: str, name: str,
    reviews: dict[str, AgentReviewResult],
    pre: float, conf: float, intel: dict,
) -> str:
    lines = [
        f"[{cid}] {name}",
        f"  Pre-consensus (weighted vote): {pre:.1f} | Confidence: {conf:.0f}%",
        f"  Adjustable range: {max(0, pre - MAX_ARBITRATOR_ADJUSTMENT):.1f} – "
        f"{min(100, pre + MAX_ARBITRATOR_ADJUSTMENT):.1f}",
    ]

    why_sel = intel.get("why_selected", [])
    why_rej = intel.get("why_rejected", [])
    if why_sel: lines.append(f"  Strengths: {' | '.join(why_sel[:3])}")
    if why_rej: lines.append(f"  Gaps:      {' | '.join(why_rej[:2])}")

    for key, label in (
        ("tech_specialist",       "Tech"),
        ("trajectory_specialist", "Trajectory"),
        ("behavioral_specialist", "Behavioral"),
    ):
        r = reviews.get(key)
        if r:
            lines.append(
                f"  {label}: {r.score:.0f}/100 | {(r.rationale or '')[:120]} | "
                f"pros={r.pros[:1]} cons={r.cons[:1]}"
            )

    return "\n".join(lines)


def _build_prompt(jd_signals: JDSignals, batch: list) -> str:
    tw, trw, bw = _domain_weights(jd_signals.domain)
    batch_ids   = [cid for cid, *_ in batch]

    block = "\n\n".join(
        _format_candidate(cid, name, reviews, pre, conf, intel)
        for cid, name, reviews, pre, conf, intel in batch
    )

    p = _PROMPT_TEMPLATE
    p = p.replace("__ROLE_TITLE__",       jd_signals.role_title)
    p = p.replace("__SENIORITY__",         jd_signals.seniority)
    p = p.replace("__DOMAIN__",            jd_signals.domain)
    p = p.replace("__IDEAL_SUMMARY__",     jd_signals.ideal_candidate_summary[:350])
    p = p.replace("__TECH_PCT__",          str(int(tw * 100)))
    p = p.replace("__TRAJ_PCT__",          str(int(trw * 100)))
    p = p.replace("__BEHAV_PCT__",         str(int(bw * 100)))
    p = p.replace("__BATCH_IDS__",         ", ".join(batch_ids))
    p = p.replace("__CANDIDATES_BLOCK__",  block)
    p = p.replace("__MAX_ADJ__",           str(int(MAX_ARBITRATOR_ADJUSTMENT)))
    p = p.replace("__N__",                 str(len(batch)))
    return p


def _clamp(arb: float, pre: float, hard_reason: bool = False) -> float:
    if hard_reason:
        return round(max(0.0, min(100.0, arb)), 2)
    lo = pre - MAX_ARBITRATOR_ADJUSTMENT
    hi = pre + MAX_ARBITRATOR_ADJUSTMENT
    return round(max(lo, min(hi, arb)), 2)


def _fallback(cid: str, reviews: dict, intel: dict, domain: str, pre: float, conf: float) -> ArbitratorVerdict:
    return ArbitratorVerdict(
        candidate_id=cid, consensus_score=pre, confidence=conf,
        strengths=intel.get("why_selected", ["Weighted specialist consensus"]),
        risks=intel.get("why_rejected", ["Arbitrator unavailable; score is weighted average"]),
        alternatives=[],
    )


def run_arbitrator(
    jd_signals: JDSignals,
    candidate_reviews: list[tuple[str, str, dict[str, AgentReviewResult]]],
    candidate_intel_map: dict[str, dict] | None = None,
) -> dict[str, ArbitratorVerdict]:
    if not candidate_reviews:
        return {}

    intel_map = candidate_intel_map or {}
    results: dict[str, ArbitratorVerdict] = {}

    enriched = []
    for cid, name, reviews in candidate_reviews:
        pre  = _compute_weighted_vote(reviews, jd_signals.domain)
        conf = _compute_confidence(reviews)
        intel = intel_map.get(cid, {})
        enriched.append((cid, name, reviews, pre, conf, intel))

    batches = [enriched[i:i + ARBITRATOR_BATCH_SIZE] for i in range(0, len(enriched), ARBITRATOR_BATCH_SIZE)]

    for batch in batches:
        prompt      = _build_prompt(jd_signals, batch)
        expected    = [cid for cid, *_ in batch]
        pre_map     = {cid: pre  for cid, _, _, pre, _,    _ in batch}
        conf_map    = {cid: conf for cid, _, _, _,   conf, _ in batch}

        try:
            raw      = _call_llm(prompt, max_tokens=4096, model=_ARBITRATOR_MODEL)
            data     = json.loads(_strip_fences(raw))
            verdicts = data.get("verdicts", [])

            batch_results: dict[str, ArbitratorVerdict] = {}

            for item in verdicts:
                cid = str(item.get("candidate_id", ""))
                if cid not in expected:
                    continue

                pre   = pre_map[cid]
                conf  = conf_map[cid]
                risks = [str(r) for r in item.get("risks", [])]

                hard_reason = any(
                    kw in " ".join(risks).lower()
                    for kw in ("zero experience", "no relevant", "completely unrelated",
                               "wrong domain", "hard disqualif", "no evidence of")
                )

                final = _clamp(
                    float(item.get("adjusted_score", pre)), pre, hard_reason
                )

                safe_alts = [
                    str(a) for a in item.get("alternatives", [])
                    if str(a) in expected and str(a) != cid
                ]

                intel = next((i for c, _, _, _, _, i in batch if c == cid), {})
                merged_str  = list(dict.fromkeys(intel.get("why_selected", []) + [str(s) for s in item.get("strengths", [])]))[:5]
                merged_risk = list(dict.fromkeys(intel.get("why_rejected", []) + risks))[:4]

                batch_results[cid] = ArbitratorVerdict(
                    candidate_id=cid, consensus_score=final, confidence=conf,
                    strengths=merged_str, risks=merged_risk, alternatives=safe_alts,
                )

            for cid, name, reviews, pre, conf, intel in batch:
                if cid not in batch_results:
                    batch_results[cid] = _fallback(cid, reviews, intel, jd_signals.domain, pre, conf)

            results.update(batch_results)

        except Exception as e:
            logger.error("arbitrator_batch_failed", error=str(e))
            for cid, name, reviews, pre, conf, intel in batch:
                results[cid] = _fallback(cid, reviews, intel, jd_signals.domain, pre, conf)

    return results