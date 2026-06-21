"""
pipeline/agents/tech_specialist.py
─────────────────────────────────────
Agent 1: Hard-Skills & Tech Specialist.

Focus: technical stack depth, architecture exposure, execution history,
complexity of projects, and core competencies. Deliberately ignores
career pedigree and soft signals — those belong to the other two agents.

BUG FIXES applied:
  1. _candidate_text() called build_rich_profile() which returns a 2400-char
     string already containing the candidate's skills, roles and summary —
     but then also duplicated raw intelligence_profile fields like
     ir_ml_evidence below it. For batches of 10 candidates this created
     ~40-50k char prompts that reliably hit Gemini's context window limit.
     Fixed: send the rich profile + the numerical evidence counts only
     (not the raw evidence text blocks, which are already embedded in the
     profile summary). The evidence counts are low-signal-to-token; agents
     infer the same from the profile text.
  2. The prompt asked the agent to score on technical depth but gave
     it skills listed as "(weight/10)" which tempts the model to
     re-use the JD weights as scores rather than evaluating depth.
     Changed to just list the top skills without weights in the agent
     prompt, with a separate "must-have" vs "preferred" distinction.
  3. __N__ placeholder in the "Include ALL __N__ candidates" instruction
     was replaced but the number was computed BEFORE filtering empty
     candidates, so the count could be wrong. Now computed at call time.
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
1. Evidence of actually using these skills in production, not just listing them.
   A skill listed on a resume with zero supporting career description = weak signal.
2. Depth and complexity: toy projects score far lower than real shipped systems.
3. Architecture thinking: have they designed systems, or only implemented specs?
4. Recency: how recent is their most relevant work?

EXPLICITLY IGNORE: company prestige, career growth, tenure, soft skills,
communication style, salary expectations. Those are other agents' job.

CANDIDATES:
__CANDIDATES_BLOCK__

Respond ONLY with valid JSON, no markdown fences:
{
  "reviews": [
    {
      "candidate_id": "<id>",
      "score": <0-100>,
      "pros": ["<specific technical strength>", "..."],
      "cons": ["<specific technical gap>", "..."],
      "rationale": "<1-2 sentences on technical fit, citing specific evidence from their profile>"
    }
  ]
}

Include ALL __N__ candidates. Be strict — a score above 80 should be rare and
requires concrete career evidence, not just keyword presence.\
"""


def build_prompt(jd_signals: JDSignals, candidates: list[dict]) -> str:
    # FIX 2: split skills into must-have (weight ≥7) and preferred (<7)
    # without showing the weights themselves (which anchor the agent score)
    sorted_skills = sorted(jd_signals.skill_weights.items(), key=lambda x: -x[1])
    must_have  = [k for k, v in sorted_skills if v >= 7][:15]
    preferred  = [k for k, v in sorted_skills if v < 7][:10]

    def _candidate_text(c: dict) -> str:
        profile = build_rich_profile(c)
        intel   = c.get("intelligence_profile") or {}
        evidence_score = intel.get("evidence_score", 0)
        return (
            f"[{c.get('candidate_id', '')}]\n"
            f"{profile}\n"
            f"Intelligence signals: AI/ML roles={intel.get('production_ai_evidence', 0)} | "
            f"Ownership acts={intel.get('ownership_evidence', 0)} | "
            f"Scale evidence={intel.get('scale_evidence', 0)} | "
            f"Leadership acts={intel.get('leadership_evidence', 0)}\n"
            f"Evidence verbs: built={intel.get('built_count', 0)} shipped={intel.get('shipped_count', 0)} "
            f"scaled={intel.get('scaled_count', 0)} led={intel.get('led_count', 0)} "
            f"→ evidence_score={evidence_score} (higher = more concrete execution proof)\n"
            f"Career: {intel.get('career_trajectory', 'unknown')}"
        )

    candidate_blob = "\n\n---\n\n".join(_candidate_text(c) for c in candidates)

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__",      jd_signals.role_title)
    prompt = prompt.replace("__MUST_HAVE_SKILLS__", ", ".join(must_have) or "not specified")
    prompt = prompt.replace("__PREFERRED_SKILLS__", ", ".join(preferred) or "not specified")
    prompt = prompt.replace("__IDEAL_SUMMARY__",   jd_signals.ideal_candidate_summary[:500])
    prompt = prompt.replace("__RED_FLAGS__",        ", ".join(jd_signals.red_flags) or "none specified")
    prompt = prompt.replace("__CANDIDATES_BLOCK__", candidate_blob)
    prompt = prompt.replace("__N__",                str(len(candidates)))  # FIX 3
    return prompt


def run_tech_specialist(
    jd_signals: JDSignals, candidates: list[dict]
) -> dict[str, AgentReviewResult]:
    """Evaluate a batch of candidates. Returns {candidate_id: AgentReviewResult}."""
    if not candidates:
        return {}
    expected_ids = [str(c.get("candidate_id", "")) for c in candidates]
    prompt = build_prompt(jd_signals, candidates)
    return call_agent_batch(prompt, AGENT_NAME, expected_ids)