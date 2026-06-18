"""
pipeline/agents/tech_specialist.py
─────────────────────────────────────
Agent 1: Hard-Skills & Tech Specialist.

Focus: technical stack depth, architecture exposure, execution history,
complexity of projects, and core competencies. Deliberately ignores
career pedigree and soft signals — those belong to the other two agents.
"""

from app.pipeline.agents.base import AgentReviewResult, call_agent_batch
from app.pipeline.jd_analyzer import JDSignals
from app.pipeline.parse_candidates import build_rich_profile

AGENT_NAME = "tech_specialist"

_PROMPT_TEMPLATE = """You are the Hard-Skills & Tech Specialist on a recruitment panel. You evaluate
candidates PURELY on technical depth — nothing else.

ROLE: __ROLE_TITLE__
KEY SKILLS REQUIRED: __SKILLS_LIST__
IDEAL CANDIDATE PROFILE: __IDEAL_SUMMARY__

Your evaluation criteria:
- Depth of relevant technical stack (not just keyword presence — evidence of real use)
- Architecture and systems exposure (have they built/scaled something non-trivial?)
- Complexity of projects described (toy projects vs. production systems)
- Core competency match to the specific skills this role needs

EXPLICITLY IGNORE: company prestige, career growth, tenure, soft skills, communication style.
Those are scored by other specialists — scoring them here is out of scope.

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
      "rationale": "<1-2 sentences on technical fit specifically>"
    }
  ]
}

Include ALL __N__ candidates."""


def build_prompt(jd_signals: JDSignals, candidates: list[dict]) -> str:
    skills_list = ", ".join(
        f"{k} ({v}/10)" for k, v in sorted(jd_signals.skill_weights.items(), key=lambda x: -x[1])[:20]
    )
    candidates_block = "\n\n".join(
        f"[{c.get('candidate_id', '')}]\n{build_rich_profile(c)}"
        for c in candidates
    )

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__", jd_signals.role_title)
    prompt = prompt.replace("__SKILLS_LIST__", skills_list)
    prompt = prompt.replace("__IDEAL_SUMMARY__", jd_signals.ideal_candidate_summary[:600])
    prompt = prompt.replace("__CANDIDATES_BLOCK__", candidates_block)
    prompt = prompt.replace("__N__", str(len(candidates)))
    return prompt


def run_tech_specialist(jd_signals: JDSignals, candidates: list[dict]) -> dict[str, AgentReviewResult]:
    """Evaluate a batch of candidates. Returns {candidate_id: AgentReviewResult}."""
    if not candidates:
        return {}
    expected_ids = [str(c.get("candidate_id", "")) for c in candidates]
    prompt = build_prompt(jd_signals, candidates)
    return call_agent_batch(prompt, AGENT_NAME, expected_ids)
