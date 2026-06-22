"""
pipeline/agents/trajectory_specialist.py
────────────────────────────────────────────
Agent 2: Pedigree & Growth Trajectory Specialist.

Tier 3 rewrite: sees career progression, promotion history, job stability,
learning velocity. NOT technical skill depth.
"""

from __future__ import annotations

from app.pipeline.agents.base import AgentReviewResult, call_agent_batch
from app.pipeline.jd_analyzer import JDSignals
from app.pipeline.parse_candidates import build_rich_profile

AGENT_NAME = "trajectory_specialist"


def _ownership_label(w: float) -> str:
    if w >= 0.8:
        return "high — must demonstrate full autonomous ownership of meaningful systems"
    if w >= 0.5:
        return "medium — should show some independent initiative and end-to-end ownership"
    return "low — guided execution with structured direction is acceptable"


def _leadership_label(w: float) -> str:
    if w >= 0.8:
        return "high — must have team lead or mentorship evidence"
    if w >= 0.5:
        return "medium — some mentoring or cross-functional influence is valuable"
    return "low — pure individual contributor track is fine"


_PROMPT_TEMPLATE = """\
You are the Pedigree & Growth Trajectory Specialist on a recruitment panel.
You evaluate candidates PURELY on career trajectory — nothing else.

ROLE: __ROLE_TITLE__ (__SENIORITY__ level)
DOMAIN: __DOMAIN__
COMPANY STAGE: __COMPANY_STAGE__
OWNERSHIP EXPECTATION: __OWNERSHIP_LABEL__
LEADERSHIP EXPECTATION: __LEADERSHIP_LABEL__
RED FLAGS TO WATCH FOR: __RED_FLAGS__

Your evaluation criteria:
1. CAREER VELOCITY — clear evidence of promotions, scope expansion, increasing responsibility.
   The trajectory field shows oldest→newest. "Analyst → Engineer → Senior → Staff" is positive.
2. COMPANY QUALITY — relative to THIS role (not a universal "bigger = better" bias).
   A Series-A startup veteran may outrank a Big-Tech CRUD developer for a founding-team role.
3. TENURE STABILITY — stints <12 months everywhere suggest serial job-hopping; flag it.
   One short stint is fine. Three in a row is a red flag.
4. LEARNING VELOCITY — does each role show scope/complexity growth?
   Stagnation (same role level for 5+ years) is a concern for growth-stage companies.
5. OWNERSHIP FIT — does history show they drive things end-to-end, or wait for direction?
6. LEADERSHIP FIT — do they have evidence of mentoring or growing a team?

NOTE: The career trajectory field reads oldest→newest. Left = earliest role. Right = current.

EXPLICITLY IGNORE: specific technical skill depth, GitHub activity, communication style.
Focus on growth pattern and company context.

CANDIDATES (trajectory signals):
__CANDIDATES_BLOCK__

Respond ONLY with valid JSON, no markdown fences:
{
  "reviews": [
    {
      "candidate_id": "<id>",
      "score": <0-100>,
      "pros": ["<specific trajectory strength>", "..."],
      "cons": ["<specific trajectory concern>", "..."],
      "rationale": "<1-2 sentences on trajectory fit, citing specific career evidence.>"
    }
  ]
}

Include ALL __N__ candidates.\
"""


def _candidate_text(c: dict) -> str:
    profile = build_rich_profile(c)
    intel   = c.get("intelligence_profile") or {}

    why_selected = intel.get("why_selected", [])
    why_rejected = intel.get("why_rejected", [])

    return (
        f"[{c.get('candidate_id', '')}]\n"
        f"{profile}\n\n"
        f"CAREER TRAJECTORY (oldest→newest): {intel.get('career_trajectory', 'unknown')}\n"
        f"Ownership evidence: {intel.get('ownership_evidence', 0)} roles with end-to-end ownership language\n"
        f"Leadership evidence: {intel.get('leadership_evidence', 0)} roles with mentoring/leading signals\n"
        f"Scale evidence: {intel.get('scale_evidence', 0)} roles with production/scale signals\n"
        f"led_count (jobs where they led/managed): {intel.get('led_count', 0)}\n\n"
        f"Pre-computed trajectory signals:\n"
        f"  Strong: {'; '.join(why_selected[:2]) or 'none'}\n"
        f"  Concerns: {'; '.join(why_rejected[:2]) or 'none'}"
    )


def build_prompt(jd_signals: JDSignals, candidates: list[dict]) -> str:
    candidate_blob = "\n\n---\n\n".join(_candidate_text(c) for c in candidates)

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__",      jd_signals.role_title)
    prompt = prompt.replace("__SENIORITY__",        jd_signals.seniority)
    prompt = prompt.replace("__DOMAIN__",           jd_signals.domain)
    prompt = prompt.replace("__COMPANY_STAGE__",    jd_signals.company_stage)
    prompt = prompt.replace("__OWNERSHIP_LABEL__",  _ownership_label(jd_signals.ownership_weight))
    prompt = prompt.replace("__LEADERSHIP_LABEL__", _leadership_label(jd_signals.leadership_weight))
    prompt = prompt.replace("__RED_FLAGS__",         ", ".join(jd_signals.red_flags) or "none specified")
    prompt = prompt.replace("__CANDIDATES_BLOCK__", candidate_blob)
    prompt = prompt.replace("__N__",                str(len(candidates)))
    return prompt


def run_trajectory_specialist(
    jd_signals: JDSignals, candidates: list[dict]
) -> dict[str, AgentReviewResult]:
    if not candidates:
        return {}
    expected_ids = [str(c.get("candidate_id", "")) for c in candidates]
    prompt = build_prompt(jd_signals, candidates)
    return call_agent_batch(prompt, AGENT_NAME, expected_ids)