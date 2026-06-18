"""
pipeline/agents/trajectory_specialist.py
────────────────────────────────────────────
Agent 2: Pedigree & Growth Trajectory Specialist.

Focus: career velocity (promotions), experience at high-growth vs.
enterprise structures, tenure stability, and educational alignment.
"""

from app.pipeline.agents.base import AgentReviewResult, call_agent_batch
from app.pipeline.jd_analyzer import JDSignals
from app.pipeline.parse_candidates import build_rich_profile

AGENT_NAME = "trajectory_specialist"

_PROMPT_TEMPLATE = """You are the Pedigree & Growth Trajectory Specialist on a recruitment panel.
You evaluate candidates PURELY on career trajectory — nothing else.

ROLE: __ROLE_TITLE__ (__SENIORITY__ level)
DOMAIN: __DOMAIN__

Your evaluation criteria:
- Career velocity: evidence of promotions, expanding scope, increasing responsibility
- Company quality: high-growth startups vs. stable enterprises vs. consulting shops —
  weigh this relative to what THIS role needs, not a universal "better company" bias
- Tenure stability: are stints long enough to show real impact, or is this a job-hopper?
- Educational alignment: does their academic background support this role, and how strong
  is the institution given what's stated?

EXPLICITLY IGNORE: specific technical skill depth, GitHub activity, communication style.
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
      "rationale": "<1-2 sentences on trajectory fit specifically>"
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
    prompt = prompt.replace("__SENIORITY__", jd_signals.seniority)
    prompt = prompt.replace("__DOMAIN__", jd_signals.domain)
    prompt = prompt.replace("__CANDIDATES_BLOCK__", candidates_block)
    prompt = prompt.replace("__N__", str(len(candidates)))
    return prompt


def run_trajectory_specialist(jd_signals: JDSignals, candidates: list[dict]) -> dict[str, AgentReviewResult]:
    if not candidates:
        return {}
    expected_ids = [str(c.get("candidate_id", "")) for c in candidates]
    prompt = build_prompt(jd_signals, candidates)
    return call_agent_batch(prompt, AGENT_NAME, expected_ids)
