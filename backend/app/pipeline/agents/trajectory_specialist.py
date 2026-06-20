"""
pipeline/agents/trajectory_specialist.py
────────────────────────────────────────────
Agent 2: Pedigree & Growth Trajectory Specialist.

Focus: career velocity (promotions), experience at high-growth vs.
enterprise structures, tenure stability, and educational alignment.

BUG FIXES applied:
  1. Same oversized prompt problem as tech_specialist — intelligence
     profile raw evidence blocks removed (already in rich profile).
  2. Prompt told the agent what ownership_weight and leadership_weight
     mean as float values (0.0–1.0) but the agent consistently treated
     them as binary booleans in its reasoning. Changed to descriptive
     categories instead of raw floats.
  3. career_trajectory string was built in reverse order in the original
     intelligence_profile.py (newest→oldest), making it look like
     candidates were descending in seniority. Fixed in intelligence_profile
     (oldest→newest now), but also added a note in the prompt so agents
     read trajectory correctly as "first role → latest role".
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
- Career velocity: clear evidence of promotions, scope expansion, increasing responsibility
- Company quality relative to THIS role (not a universal "bigger = better" bias):
  a Series-A startup veteran may outrank a Big-Tech CRUD developer for a founding-team role
- Tenure stability: stints <12 months everywhere suggest serial job-hopping; flag it
- Educational alignment: does their background support the technical depth this role needs?
- Ownership fit: does history show they drive things end-to-end, or wait for direction?
  (see ownership expectation above)
- Leadership fit: do they have evidence of mentoring or leading others?
  (see leadership expectation above)

NOTE ON TRAJECTORY: The career trajectory field shows roles oldest→newest (left=earliest).
A trajectory that goes Analyst→Engineer→Senior→Staff IS positive progression, even if
the current title is in the middle of the list.

EXPLICITLY IGNORE: specific technical skill depth, GitHub activity, communication style.

CANDIDATES:
__CANDIDATES_BLOCK__

Respond ONLY with valid JSON, no markdown fences:
{
  "reviews": [
    {
      "candidate_id": "<id>",
      "score": <0-100>,
      "pros": ["<short phrase>", "..."],
      "cons": ["<short phrase>", "..."],
      "rationale": "<1-2 sentences on trajectory fit, citing specific career evidence>"
    }
  ]
}

Include ALL __N__ candidates.\
"""


def build_prompt(jd_signals: JDSignals, candidates: list[dict]) -> str:
    def _candidate_text(c: dict) -> str:
        profile = build_rich_profile(c)
        intel   = c.get("intelligence_profile") or {}
        return (
            f"[{c.get('candidate_id', '')}]\n"
            f"{profile}\n"
            f"Career trajectory (oldest→newest): {intel.get('career_trajectory', 'unknown')}\n"
            f"Ownership signals count: {intel.get('ownership_evidence', 0)} | "
            f"Leadership signals count: {intel.get('leadership_evidence', 0)}"
        )

    candidate_blob = "\n\n---\n\n".join(_candidate_text(c) for c in candidates)

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__",       jd_signals.role_title)
    prompt = prompt.replace("__SENIORITY__",         jd_signals.seniority)
    prompt = prompt.replace("__DOMAIN__",            jd_signals.domain)
    prompt = prompt.replace("__COMPANY_STAGE__",     jd_signals.company_stage)
    prompt = prompt.replace("__OWNERSHIP_LABEL__",   _ownership_label(jd_signals.ownership_weight))
    prompt = prompt.replace("__LEADERSHIP_LABEL__",  _leadership_label(jd_signals.leadership_weight))
    prompt = prompt.replace("__RED_FLAGS__",          ", ".join(jd_signals.red_flags) or "none specified")
    prompt = prompt.replace("__CANDIDATES_BLOCK__",  candidate_blob)
    prompt = prompt.replace("__N__",                 str(len(candidates)))
    return prompt


def run_trajectory_specialist(
    jd_signals: JDSignals, candidates: list[dict]
) -> dict[str, AgentReviewResult]:
    if not candidates:
        return {}
    expected_ids = [str(c.get("candidate_id", "")) for c in candidates]
    prompt = build_prompt(jd_signals, candidates)
    return call_agent_batch(prompt, AGENT_NAME, expected_ids)