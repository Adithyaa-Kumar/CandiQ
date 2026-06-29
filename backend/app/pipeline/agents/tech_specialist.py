"""
pipeline/agents/tech_specialist.py
────────────────────────────────────
Agent 1: Hard-Skills & Technical Depth Specialist.

SCORING ANCHORS (hardened to prevent 40-point scores for irrelevant candidates)
──────────────────────────────────────────────────────────────────────────────
90–100: Production AI/ML at scale. Evidence of shipping ranked/retrieval/generative
        systems at meaningful scale (millions of users). Quantified impact. Deep
        expertise in ≥3 must-have skills with career evidence.

75–89:  Strong AI/ML background. 2+ production AI roles. Clear domain expertise.
        Most must-have skills demonstrated. Some impact evidence.

60–74:  Solid ML background. 1-2 production roles with relevant work.
        Has core skills. Limited scale evidence.

40–59:  Adjacent background. Adjacent domain (e.g., data analyst with ML exposure).
        Knows some skills but limited production evidence.

20–39:  Weak. Has some relevant keywords but no career evidence of using them.
        Listed Python but no ML work.

0–19:   Irrelevant. Wrong domain entirely. No meaningful technical overlap.
        Score HERE if: graphic designer, project manager, customer support,
        operations manager — anyone with zero ML/AI career evidence.

RULE: Never give > 30 to a candidate with zero AI/ML career descriptions.
RULE: Never give > 50 to a candidate with zero production AI roles.
RULE: Score > 80 requires both impact evidence AND scale evidence.
"""

from __future__ import annotations

from app.pipeline.agents.base import AgentReviewResult, call_agent_batch
from app.pipeline.jd_analyzer import JDSignals

AGENT_NAME = "tech_specialist"

_PROMPT_TEMPLATE = """\
You are the Hard-Skills & Technical Depth Specialist on a recruitment panel.
You score ONLY technical depth — ignore company names, soft skills, and career growth.

ROLE: __ROLE_TITLE__
DOMAIN: __DOMAIN__

MUST-HAVE SKILLS (non-negotiable for this role):
__MUST_HAVE_SKILLS__

PREFERRED SKILLS (differentiators):
__PREFERRED_SKILLS__

IDEAL CANDIDATE: __IDEAL_SUMMARY__

═══════════════════════════════════════════════════════════════
SCORING SCALE — READ CAREFULLY AND FOLLOW EXACTLY:
═══════════════════════════════════════════════════════════════

90–100: Multiple production AI/ML systems shipped at scale. Quantified impact
        (CTR, latency, revenue numbers). Deep expertise in ≥3 must-have skills.
        Scale evidence (millions of users, TB of data, thousands of QPS).

75–89:  2+ production AI/ML roles. Domain expertise clear. Most must-have skills
        demonstrated in career descriptions (not just listed). Some impact evidence.

60–74:  1-2 roles with relevant AI/ML work. Core skills present with some career
        evidence. Limited scale. Solid foundation but not deep.

40–59:  Adjacent domain. Data analyst with ML exposure, or software engineer who
        touched some ML tooling. Skills listed but limited career evidence of use.

20–39:  Wrong domain leaning toward relevant. Has some tech background but in an
        unrelated area. Knows Python but no ML/AI work.

0–19:   IRRELEVANT DOMAIN. Use this range for:
        - Graphic designers, UX designers
        - Project managers, scrum masters
        - Customer support, operations, HR
        - Sales, marketing
        - Anyone whose career descriptions show ZERO AI/ML work
        A candidate who listed "Python" on their profile but works as a graphic
        designer scores in this range.

ABSOLUTE RULES:
- If production_ai_evidence == 0: score must be ≤ 35
- If production_ai_evidence == 1 and no impact evidence: score must be ≤ 65
- If all three of (production_ai_evidence > 1, impact_evidence > 0, scale_evidence > 0)
  are true: score may go above 80
- Never give a score that would confuse a recruiter about fit quality

═══════════════════════════════════════════════════════════════

CANDIDATES:
__CANDIDATES_BLOCK__

Respond ONLY with valid JSON, no markdown:
{
  "reviews": [
    {
      "candidate_id": "<id>",
      "score": <integer 0-100 following the scale above EXACTLY>,
      "pros": ["<specific technical strength with career evidence>", "..."],
      "cons": ["<specific technical gap or missing evidence>", "..."],
      "rationale": "<cite production_ai_evidence count, impact/scale evidence, and specific must-have skills matched>"
    }
  ]
}

Include ALL __N__ candidates.\
"""


def _candidate_block(c: dict) -> str:
    intel = c.get("intelligence_profile") or {}
    cid   = c.get("candidate_id", "")
    prof  = c.get("profile", {})
    name  = prof.get("anonymized_name", "Unknown")
    title = prof.get("current_title", "Unknown")
    yoe   = prof.get("years_of_experience", 0)

    skills = ", ".join(intel.get("key_skills", [])[:20]) or "none listed"

    ir_snippets  = intel.get("ir_ml_evidence",    [])[:3]
    imp_snippets = intel.get("impact_signals",    [])[:3]
    scl_snippets = intel.get("scale_signals",     [])[:2]
    own_snippets = intel.get("ownership_signals", [])[:2]

    ir_str  = " | ".join(s[:200] for s in ir_snippets)  or "NONE FOUND"
    imp_str = " | ".join(s[:150] for s in imp_snippets) or "NONE FOUND"
    scl_str = " | ".join(s[:120] for s in scl_snippets) or "NONE FOUND"
    own_str = " | ".join(s[:150] for s in own_snippets) or "NONE FOUND"

    prod_ai = intel.get("production_ai_evidence", 0)
    impact  = intel.get("impact_evidence", 0)
    scale   = intel.get("scale_evidence",  0)
    built   = intel.get("built_count",     0)
    shipped = intel.get("shipped_count",   0)

    # Determine score ceiling hint for the model
    if prod_ai == 0:
        hint = "⚠ ZERO AI/ML career evidence — score MUST be ≤ 35"
    elif prod_ai == 1 and impact == 0:
        hint = "1 AI/ML role, no quantified impact — score MUST be ≤ 65"
    elif prod_ai >= 2 and impact >= 1 and scale >= 1:
        hint = "Strong evidence profile — may score 80+"
    else:
        hint = "Moderate evidence — use 40–74 range"

    return (
        f"[{cid}] {name} | {title} | {yoe} yrs\n"
        f"Declared skills: {skills}\n"
        f"Career trajectory: {intel.get('career_trajectory', 'unknown')}\n"
        f"Evidence counts: prod_ai={prod_ai} impact={impact} scale={scale} "
        f"built={built} shipped={shipped}\n"
        f"Scoring hint: {hint}\n\n"
        f"AI/ML CAREER EVIDENCE ({prod_ai} roles):\n{ir_str}\n\n"
        f"IMPACT EVIDENCE ({impact} roles with numbers):\n{imp_str}\n\n"
        f"SCALE EVIDENCE ({scale} roles at scale):\n{scl_str}\n\n"
        f"OWNERSHIP LANGUAGE:\n{own_str}"
    )


def build_prompt(jd_signals: JDSignals, candidates: list[dict]) -> str:
    sorted_skills = sorted(jd_signals.skill_weights.items(), key=lambda x: -x[1])
    must_have = [k for k, v in sorted_skills if v >= 7][:12]
    preferred = [k for k, v in sorted_skills if v < 7][:8]

    candidate_blob = "\n\n---\n\n".join(_candidate_block(c) for c in candidates)

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__",       jd_signals.role_title)
    prompt = prompt.replace("__DOMAIN__",            jd_signals.domain)
    prompt = prompt.replace("__MUST_HAVE_SKILLS__",  ", ".join(must_have) or "not specified")
    prompt = prompt.replace("__PREFERRED_SKILLS__",  ", ".join(preferred) or "not specified")
    prompt = prompt.replace("__IDEAL_SUMMARY__",     jd_signals.ideal_candidate_summary[:500])
    prompt = prompt.replace("__CANDIDATES_BLOCK__",  candidate_blob)
    prompt = prompt.replace("__N__",                 str(len(candidates)))
    return prompt


def run_tech_specialist(jd_signals: JDSignals, candidates: list[dict]) -> dict[str, AgentReviewResult]:
    if not candidates:
        return {}
    expected_ids = [str(c.get("candidate_id", "")) for c in candidates]
    return call_agent_batch(build_prompt(jd_signals, candidates), AGENT_NAME, expected_ids)