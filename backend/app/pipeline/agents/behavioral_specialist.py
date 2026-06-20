"""
pipeline/agents/behavioral_specialist.py
────────────────────────────────────────────
Agent 3: Behavioral & Platform Signal Specialist.

Focus: open-source activity (GitHub), thought leadership, mentorship
signals in role descriptions, communication clarity, and soft-skill
indicators detectable from profile text.
"""

from app.pipeline.agents.base import AgentReviewResult, call_agent_batch
from app.pipeline.jd_analyzer import JDSignals
from app.pipeline.parse_candidates import build_rich_profile

AGENT_NAME = "behavioral_specialist"

_PROMPT_TEMPLATE = """You are the Behavioral & Platform Signal Specialist on a recruitment panel.
You evaluate candidates PURELY on behavioral and platform-activity signals — nothing else.

ROLE: __ROLE_TITLE__
DOMAIN: __DOMAIN__
COMPANY STAGE: __COMPANY_STAGE__
OWNERSHIP EXPECTATION: __OWNERSHIP_WEIGHT__ (0.0 = guided execution, 1.0 = full autonomous ownership)
LEADERSHIP EXPECTATION: __LEADERSHIP_WEIGHT__ (0.0 = pure IC, 1.0 = must lead teams / mentor others)
RED FLAGS TO WATCH FOR: __RED_FLAGS__

Your evaluation criteria:
- Open-source / community activity: GitHub contributions, public projects, technical writing
- Thought leadership: blog posts, talks, mentoring signals mentioned in their profile text
- Mentorship indicators: language in their role descriptions suggesting they grew or led others
- Communication clarity: how clearly and specifically they describe their own work
  (vague buzzword-heavy descriptions score lower than specific, concrete ones)
- Ownership signals: do their descriptions show they drove things end-to-end, or just contributed?
  Weight this relative to the ownership_weight above.
- Initiative signals: did they propose, start, or lead things, or only respond to direction?
  Weight this relative to the leadership_weight above.

EXPLICITLY IGNORE: technical skill depth, company pedigree, years of experience.
Those are scored by other specialists.

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
      "rationale": "<1-2 sentences on behavioral fit specifically>"
    }
  ]
}

Include ALL __N__ candidates."""


def build_prompt(jd_signals: JDSignals, candidates: list[dict]) -> str:
    def _candidate_text(c):
      profile = build_rich_profile(c)

      intel = c.get("intelligence_profile") or {}

      return f"""
    [{c.get('candidate_id', '')}]

    {profile}

    === INTELLIGENCE PROFILE ===

    IR/ML Evidence:
    {intel.get("ir_ml_evidence", [])}

    Ownership Signals:
    {intel.get("ownership_signals", [])}

    Career Trajectory:
    {intel.get("career_trajectory", "")}

    Key Skills:
    {intel.get("key_skills", [])}
    """

    candidate_blob = "\n\n".join(
      _candidate_text(c)
      for c in candidates
    )


    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__", jd_signals.role_title)
    prompt = prompt.replace("__DOMAIN__", jd_signals.domain)
    prompt = prompt.replace("__COMPANY_STAGE__", jd_signals.company_stage)
    prompt = prompt.replace("__OWNERSHIP_WEIGHT__", str(round(jd_signals.ownership_weight, 2)))
    prompt = prompt.replace("__LEADERSHIP_WEIGHT__", str(round(jd_signals.leadership_weight, 2)))
    prompt = prompt.replace("__RED_FLAGS__", ", ".join(jd_signals.red_flags) or "none specified")
    prompt = prompt.replace("__CANDIDATES_BLOCK__", candidate_blob)
    prompt = prompt.replace("__N__", str(len(candidates)))
    return prompt


def run_behavioral_specialist(jd_signals: JDSignals, candidates: list[dict]) -> dict[str, AgentReviewResult]:
    if not candidates:
        return {}
    expected_ids = [str(c.get("candidate_id", "")) for c in candidates]
    prompt = build_prompt(jd_signals, candidates)
    return call_agent_batch(prompt, AGENT_NAME, expected_ids)