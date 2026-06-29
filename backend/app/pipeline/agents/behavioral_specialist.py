"""
pipeline/agents/behavioral_specialist.py
─────────────────────────────────────────
Agent 3: Behavioral & Platform Signal Specialist.
"""

from __future__ import annotations

from app.pipeline.agents.base import AgentReviewResult, call_agent_batch
from app.pipeline.jd_analyzer import JDSignals

AGENT_NAME = "behavioral_specialist"


def _ownership_label(w: float) -> str:
    if w >= 0.8: return "CRITICAL — must show strong end-to-end initiative"
    if w >= 0.5: return "Important — demonstrated initiative valued"
    return "Moderate — responsive execution acceptable"


def _leadership_label(w: float) -> str:
    if w >= 0.8: return "CRITICAL — mentoring/leading evidence required"
    if w >= 0.5: return "Valued — cross-functional influence appreciated"
    return "Not required — IC track fine"


_PROMPT_TEMPLATE = """\
You are the Behavioral & Platform Signal Specialist on a recruitment panel.
You score ONLY behavioral signals — ownership language, initiative, impact specificity.
Do NOT score technical skills or career pedigree.

ROLE: __ROLE_TITLE__
DOMAIN: __DOMAIN__
COMPANY STAGE: __COMPANY_STAGE__
OWNERSHIP: __OWNERSHIP_LABEL__
LEADERSHIP: __LEADERSHIP_LABEL__

═══════════════════════════════════════════════════════════════
SCORING SCALE:
═══════════════════════════════════════════════════════════════

85–100: Consistently strong builder language across ALL roles. High ownership
        AND impact evidence. Quantified outcomes in multiple roles.
        Clear initiative signals (launched, founded, pioneered).

70–84:  Strong behavioral signals. Good ownership language. Some quantified
        impact. Initiative evident in most roles.

55–69:  Mixed signals. Some ownership language but also passive language
        ("contributed to", "assisted with"). Some impact but not quantified.

35–54:  Weak behavioral signals. Mostly passive language. Vague descriptions.
        "Worked on team" without specifying their role or contribution.

15–34:  Very weak. Descriptions are generic or administrative. No evidence
        of measuring outcomes. Reactive rather than proactive.

0–14:   No behavioral signals relevant to this role type. Career descriptions
        are entirely in a different behavioral mode (e.g., a customer support
        rep whose "initiative" was answering tickets faster).
        Use this range for candidates from entirely irrelevant domains.

ABSOLUTE RULES:
- ownership_evidence = 0 AND impact_evidence = 0: score must be ≤ 30
- ownership_score = 0 AND impact_score = 0: cap at 25
- Passive language only ("helped", "assisted", "supported"): deduct 15

═══════════════════════════════════════════════════════════════

CANDIDATES:
__CANDIDATES_BLOCK__

Respond ONLY with valid JSON, no markdown:
{
  "reviews": [
    {
      "candidate_id": "<id>",
      "score": <integer 0-100>,
      "pros": ["<specific behavioral strength with evidence>"],
      "cons": ["<specific behavioral gap>"],
      "rationale": "<cite ownership/impact counts, specific language examples>"
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

    summary = prof.get("summary", "")[:400]

    own_snippets = intel.get("ownership_signals", [])
    imp_snippets = intel.get("impact_signals",    [])

    own_str = " | ".join(s[:150] for s in own_snippets[:3]) or "NONE DETECTED"
    imp_str = " | ".join(s[:150] for s in imp_snippets[:3]) or "NONE DETECTED"

    ownership  = intel.get("ownership_evidence",  0)
    impact     = intel.get("impact_evidence",     0)
    leadership = intel.get("leadership_evidence", 0)
    built      = intel.get("built_count",  0)
    shipped    = intel.get("shipped_count", 0)
    scaled     = intel.get("scaled_count", 0)
    own_score  = intel.get("ownership_score", 0)
    imp_score  = intel.get("impact_score",    0)

    gh_score  = sigs.get("github_activity_score", -1)
    gh_str    = f"{gh_score:.0f}/100" if gh_score and gh_score > 0 else "not available"
    resp_rate = sigs.get("recruiter_response_rate", 0)
    otw       = "actively looking" if sigs.get("open_to_work_flag") else "passive"

    # Score ceiling hint
    if ownership == 0 and impact == 0:
        hint = "⚠ ZERO ownership AND impact evidence — score MUST be ≤ 30"
    elif own_score == 0 and imp_score == 0:
        hint = "⚠ ownership_score=0 and impact_score=0 — cap at 25"
    elif ownership >= 3 and impact >= 2:
        hint = "Strong behavioral profile — may score 75+"
    else:
        hint = "Moderate behavioral evidence — use 40–70 range"

    return (
        f"[{cid}] {name}\n"
        f"Self-summary: {summary}\n"
        f"Evidence counts: ownership={ownership} impact={impact} leadership={leadership} "
        f"built={built} shipped={shipped} scaled={scaled}\n"
        f"Scores: ownership_score={own_score} impact_score={imp_score}\n"
        f"Scoring hint: {hint}\n\n"
        f"OWNERSHIP LANGUAGE ({ownership} roles):\n{own_str}\n\n"
        f"IMPACT EVIDENCE ({impact} roles with quantified outcomes):\n{imp_str}\n\n"
        f"Platform: GitHub={gh_str} | Status={otw} | Response={int(resp_rate*100)}%"
    )


def build_prompt(jd_signals: JDSignals, candidates: list[dict]) -> str:
    candidate_blob = "\n\n---\n\n".join(_candidate_block(c) for c in candidates)

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__",       jd_signals.role_title)
    prompt = prompt.replace("__DOMAIN__",            jd_signals.domain)
    prompt = prompt.replace("__COMPANY_STAGE__",     jd_signals.company_stage)
    prompt = prompt.replace("__OWNERSHIP_LABEL__",   _ownership_label(jd_signals.ownership_weight))
    prompt = prompt.replace("__LEADERSHIP_LABEL__",  _leadership_label(jd_signals.leadership_weight))
    prompt = prompt.replace("__CANDIDATES_BLOCK__",  candidate_blob)
    prompt = prompt.replace("__N__",                 str(len(candidates)))
    return prompt


def run_behavioral_specialist(jd_signals: JDSignals, candidates: list[dict]) -> dict[str, AgentReviewResult]:
    if not candidates:
        return {}
    expected_ids = [str(c.get("candidate_id", "")) for c in candidates]
    return call_agent_batch(build_prompt(jd_signals, candidates), AGENT_NAME, expected_ids)