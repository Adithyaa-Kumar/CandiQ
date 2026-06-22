"""
pipeline/agents/tech_specialist.py
─────────────────────────────────────
Agent 1: Hard-Skills & Tech Specialist.

Tier 3 rewrite: specialist sees ONLY what's relevant to its dimension.
Tech specialist sees: production AI evidence, impact evidence, scale evidence,
technical skills. NOT career pedigree or soft signals.
"""

from __future__ import annotations

from app.pipeline.agents.base import AgentReviewResult, call_agent_batch
from app.pipeline.jd_analyzer import JDSignals
from app.pipeline.parse_candidates import build_rich_profile

AGENT_NAME = "tech_specialist"

_PROMPT_TEMPLATE = """\
You are the Hard-Skills & Tech Specialist on a recruitment panel. You evaluate
candidates PURELY on technical depth — nothing else.

ROLE: __ROLE_TITLE__

MUST-HAVE SKILLS (candidates who lack most of these are weak fits):
__MUST_HAVE_SKILLS__

PREFERRED SKILLS (differentiators between strong and average candidates):
__PREFERRED_SKILLS__

IDEAL CANDIDATE PROFILE: __IDEAL_SUMMARY__

RED FLAGS TO WATCH FOR: __RED_FLAGS__

Your evaluation criteria (in order of importance):
1. PRODUCTION AI EVIDENCE — have they shipped ML/AI systems? Count AI/ML roles.
   A candidate with 3+ production AI roles vs someone who listed skills is very different.
2. IMPACT EVIDENCE — did they quantify outcomes? "Improved CTR by 18%", "reduced latency by 40%"
   are hard signals. Vague descriptions ("worked on AI solutions") score low.
3. SCALE EVIDENCE — did they operate at scale? "Serving 50M users", "10M events/day",
   "10TB data" matters. It signals production-grade engineering judgment.
4. CAPABILITY MATCH — note: LangChain and Haystack both demonstrate RAG capability.
   Evaluate the capability demonstrated, not just the tool name.
5. DEPTH — toy projects score far lower than real shipped systems.
   A skill listed with zero supporting career evidence is weak signal.

EXPLICITLY IGNORE: company prestige, career growth, tenure, soft skills,
communication style, salary expectations. Those are other agents' job.

CANDIDATES (technical evidence only):
__CANDIDATES_BLOCK__

Respond ONLY with valid JSON, no markdown fences:
{
  "reviews": [
    {
      "candidate_id": "<id>",
      "score": <0-100>,
      "pros": ["<specific technical strength citing evidence>", "..."],
      "cons": ["<specific technical gap>", "..."],
      "rationale": "<1-2 sentences on technical fit, citing specific evidence. Mention production_ai_evidence count and impact signals.>"
    }
  ]
}

Include ALL __N__ candidates. Be strict — score above 80 requires concrete career
evidence, not just keyword presence. Score above 90 requires impact + scale evidence.\
"""


def _candidate_text(c: dict) -> str:
    intel = c.get("intelligence_profile") or {}

    # Curated technical evidence block — no career pedigree, no company names
    skill_list = ", ".join(intel.get("key_skills", [])[:20]) or "not listed"

    impact_snippets  = intel.get("impact_signals", [])[:3]
    scale_snippets   = intel.get("scale_signals", [])[:2]
    ir_snippets      = intel.get("ir_ml_evidence", [])[:3]
    ownership_snips  = intel.get("ownership_signals", [])[:2]

    impact_str  = " | ".join(s[:150] for s in impact_snippets)  or "none detected"
    scale_str   = " | ".join(s[:120] for s in scale_snippets)   or "none detected"
    ir_str      = " | ".join(s[:200] for s in ir_snippets)      or "none detected"
    ownership_str = " | ".join(s[:150] for s in ownership_snips) or "none detected"

    return (
        f"[{c.get('candidate_id', '')}] {c.get('profile', {}).get('name', 'Unknown')}\n"
        f"Technical Skills: {skill_list}\n"
        f"Career Trajectory: {intel.get('career_trajectory', 'unknown')}\n\n"
        f"PRODUCTION AI/ML EVIDENCE ({intel.get('production_ai_evidence', 0)} roles):\n{ir_str}\n\n"
        f"IMPACT EVIDENCE ({intel.get('impact_evidence', 0)} roles with quantified outcomes):\n{impact_str}\n\n"
        f"SCALE EVIDENCE ({intel.get('scale_evidence', 0)} roles with scale signals):\n{scale_str}\n\n"
        f"OWNERSHIP LANGUAGE ({intel.get('ownership_evidence', 0)} roles):\n{ownership_str}\n\n"
        f"Evidence verbs → built={intel.get('built_count',0)} shipped={intel.get('shipped_count',0)} "
        f"scaled={intel.get('scaled_count',0)} led={intel.get('led_count',0)} "
        f"→ evidence_score={intel.get('evidence_score',0)}"
    )


def build_prompt(jd_signals: JDSignals, candidates: list[dict]) -> str:
    sorted_skills = sorted(jd_signals.skill_weights.items(), key=lambda x: -x[1])
    must_have = [k for k, v in sorted_skills if v >= 7][:15]
    preferred = [k for k, v in sorted_skills if v < 7][:10]

    candidate_blob = "\n\n---\n\n".join(_candidate_text(c) for c in candidates)

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__",      jd_signals.role_title)
    prompt = prompt.replace("__MUST_HAVE_SKILLS__", ", ".join(must_have) or "not specified")
    prompt = prompt.replace("__PREFERRED_SKILLS__", ", ".join(preferred) or "not specified")
    prompt = prompt.replace("__IDEAL_SUMMARY__",   jd_signals.ideal_candidate_summary[:500])
    prompt = prompt.replace("__RED_FLAGS__",        ", ".join(jd_signals.red_flags) or "none specified")
    prompt = prompt.replace("__CANDIDATES_BLOCK__", candidate_blob)
    prompt = prompt.replace("__N__",                str(len(candidates)))
    return prompt


def run_tech_specialist(
    jd_signals: JDSignals, candidates: list[dict]
) -> dict[str, AgentReviewResult]:
    if not candidates:
        return {}
    expected_ids = [str(c.get("candidate_id", "")) for c in candidates]
    prompt = build_prompt(jd_signals, candidates)
    return call_agent_batch(prompt, AGENT_NAME, expected_ids)