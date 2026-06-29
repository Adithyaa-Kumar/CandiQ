"""
pipeline/agents/trajectory_specialist.py
──────────────────────────────────────────
Agent 2: Career Trajectory & Pedigree Specialist.
"""

from __future__ import annotations

from app.pipeline.agents.base import AgentReviewResult, call_agent_batch
from app.pipeline.jd_analyzer import JDSignals
from app.pipeline.parse_candidates import build_rich_profile

AGENT_NAME = "trajectory_specialist"


def _ownership_label(w: float) -> str:
    if w >= 0.8: return "CRITICAL — must show full autonomous ownership of meaningful systems"
    if w >= 0.5: return "Important — should demonstrate independent initiative and end-to-end ownership"
    return "Moderate — guided execution is acceptable"


def _leadership_label(w: float) -> str:
    if w >= 0.8: return "CRITICAL — must have clear team-lead or mentoring evidence"
    if w >= 0.5: return "Valued — some mentoring or cross-functional influence"
    return "Not required — pure IC is fine"


_PROMPT_TEMPLATE = """\
You are the Career Trajectory & Pedigree Specialist on a recruitment panel.
You score ONLY career growth pattern and trajectory — not technical skills.

ROLE: __ROLE_TITLE__ (__SENIORITY__)
DOMAIN: __DOMAIN__
COMPANY STAGE: __COMPANY_STAGE__
OWNERSHIP: __OWNERSHIP_LABEL__
LEADERSHIP: __LEADERSHIP_LABEL__

═══════════════════════════════════════════════════════════════
SCORING SCALE:
═══════════════════════════════════════════════════════════════

85–100: Clear upward trajectory with evidence. Scope growth at each role.
        Company quality appropriate for this role type. Strong ownership history.
        For founding-team/growth-stage: startup experience at scale preferred.

70–84:  Good trajectory. Most roles show growth. Minor concerns (one short stint,
        or one company tier below expectation) but overall positive pattern.

50–69:  Mixed trajectory. Some growth evidence but stagnation or lateral moves.
        Company quality uneven. Tenure borderline (1 short stint).

30–49:  Weak trajectory. Mostly lateral moves. Job-hopping pattern (3+ stints < 12mo).
        Or: entirely consulting background when product experience needed.

10–29:  Poor trajectory. Minimal progression. Career in entirely different domain
        (e.g., graphic designer career path, customer support progression).
        No leadership or ownership signals whatsoever.

0–9:    Wrong career track entirely. Career shows zero alignment with this role type.

ABSOLUTE RULES:
- If career_trajectory shows non-technical roles only (designer → designer → designer):
  score must be ≤ 20
- If candidate has never progressed beyond an entry-level equivalent in this domain:
  score must be ≤ 40
- Leadership evidence count = 0 AND ownership evidence = 0: deduct 10 from score

═══════════════════════════════════════════════════════════════

CANDIDATES:
__CANDIDATES_BLOCK__

Respond ONLY with valid JSON, no markdown:
{
  "reviews": [
    {
      "candidate_id": "<id>",
      "score": <integer 0-100>,
      "pros": ["<specific trajectory strength>"],
      "cons": ["<specific trajectory gap>"],
      "rationale": "<cite career_trajectory progression, company types, ownership/leadership counts>"
    }
  ]
}

Include ALL __N__ candidates.\
"""


def _candidate_block(c: dict) -> str:
    intel = c.get("intelligence_profile") or {}
    prof  = c.get("profile", {})
    sigs  = c.get("redrob_signals", {})

    cid   = c.get("candidate_id", "")
    name  = prof.get("anonymized_name", "Unknown")
    title = prof.get("current_title", "Unknown")
    yoe   = prof.get("years_of_experience", 0)

    trajectory = intel.get("career_trajectory", "unknown")
    ownership  = intel.get("ownership_evidence", 0)
    leadership = intel.get("leadership_evidence", 0)
    scale      = intel.get("scale_evidence", 0)
    led        = intel.get("led_count", 0)

    why_sel = intel.get("why_selected", [])
    why_rej = intel.get("why_rejected", [])

    profile_text = build_rich_profile(c, max_chars=1200)

    return (
        f"[{cid}] {name} | {title} | {yoe} yrs\n"
        f"Career progression (oldest→newest): {trajectory}\n"
        f"Evidence: ownership={ownership} roles | leadership={leadership} roles | "
        f"scale={scale} roles | led/managed={led} times\n"
        f"Pre-computed: {'; '.join(why_sel[:2]) or 'none'} | "
        f"Gaps: {'; '.join(why_rej[:2]) or 'none'}\n\n"
        f"{profile_text}"
    )


def build_prompt(jd_signals: JDSignals, candidates: list[dict]) -> str:
    candidate_blob = "\n\n---\n\n".join(_candidate_block(c) for c in candidates)

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__",       jd_signals.role_title)
    prompt = prompt.replace("__SENIORITY__",         jd_signals.seniority)
    prompt = prompt.replace("__DOMAIN__",            jd_signals.domain)
    prompt = prompt.replace("__COMPANY_STAGE__",     jd_signals.company_stage)
    prompt = prompt.replace("__OWNERSHIP_LABEL__",   _ownership_label(jd_signals.ownership_weight))
    prompt = prompt.replace("__LEADERSHIP_LABEL__",  _leadership_label(jd_signals.leadership_weight))
    prompt = prompt.replace("__CANDIDATES_BLOCK__",  candidate_blob)
    prompt = prompt.replace("__N__",                 str(len(candidates)))
    return prompt


def run_trajectory_specialist(jd_signals: JDSignals, candidates: list[dict]) -> dict[str, AgentReviewResult]:
    if not candidates:
        return {}
    expected_ids = [str(c.get("candidate_id", "")) for c in candidates]
    return call_agent_batch(build_prompt(jd_signals, candidates), AGENT_NAME, expected_ids)