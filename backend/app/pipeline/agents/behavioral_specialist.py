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

Your evaluation criteria:
- Open-source / community activity: GitHub contributions, public projects, technical writing
- Thought leadership: blog posts, talks, mentoring signals mentioned in their profile text
- Mentorship indicators: language in their role descriptions suggesting they grew or led others
- Communication clarity: how clearly and specifically they describe their own work
  (vague buzzword-heavy descriptions score lower than specific, concrete ones)

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
    candidates_block = "\n\n".join(
        f"[{c.get('candidate_id', '')}]\n{build_rich_profile(c)}"
        for c in candidates
    )

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__", jd_signals.role_title)
    prompt = prompt.replace("__DOMAIN__", jd_signals.domain)
    prompt = prompt.replace("__CANDIDATES_BLOCK__", candidates_block)
    prompt = prompt.replace("__N__", str(len(candidates)))
    return prompt


def run_behavioral_specialist(jd_signals: JDSignals, candidates: list[dict]) -> dict[str, AgentReviewResult]:
    if not candidates:
        return {}
    expected_ids = [str(c.get("candidate_id", "")) for c in candidates]
    prompt = build_prompt(jd_signals, candidates)
    return call_agent_batch(prompt, AGENT_NAME, expected_ids)
