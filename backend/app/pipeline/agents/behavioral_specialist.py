"""
pipeline/agents/behavioral_specialist.py
────────────────────────────────────────────
Agent 3: Behavioral & Platform Signal Specialist.

Tier 3 rewrite: sees ONLY behavioral signals — ownership language,
initiative evidence, GitHub activity, platform engagement.
NO technical skill depth, NO company pedigree.
"""

from __future__ import annotations

from app.pipeline.agents.base import AgentReviewResult, call_agent_batch
from app.pipeline.jd_analyzer import JDSignals

AGENT_NAME = "behavioral_specialist"


def _ownership_label(w: float) -> str:
    if w >= 0.8:
        return "high — must show strong end-to-end initiative and autonomous ownership"
    if w >= 0.5:
        return "medium — some demonstrated initiative valued"
    return "low — responsive execution is fine; initiative is a bonus"


def _leadership_label(w: float) -> str:
    if w >= 0.8:
        return "high — must show evidence of mentoring, leading, or scaling others"
    if w >= 0.5:
        return "medium — some mentoring/cross-functional influence appreciated"
    return "low — individual contributor mindset is perfectly acceptable"


_PROMPT_TEMPLATE = """\
You are the Behavioral & Platform Signal Specialist on a recruitment panel.
You evaluate candidates PURELY on behavioral and soft signals — nothing else.

ROLE: __ROLE_TITLE__
DOMAIN: __DOMAIN__
COMPANY STAGE: __COMPANY_STAGE__
OWNERSHIP EXPECTATION: __OWNERSHIP_LABEL__
LEADERSHIP EXPECTATION: __LEADERSHIP_LABEL__
RED FLAGS TO WATCH FOR: __RED_FLAGS__

Your evaluation criteria:
1. OWNERSHIP QUALITY — does the candidate use builder language?
   "Built X from scratch", "Owned Y end-to-end", "Led Z initiative" = HIGH ownership.
   "Contributed to", "Helped with", "Assisted in" = LOW ownership.
   Count their ownership_evidence jobs. More = stronger signal.

2. IMPACT SPECIFICITY — do they quantify what they achieved?
   "Improved CTR by 18%" >> "improved performance".
   "Reduced infra cost by $2M" >> "optimized costs".
   High impact_evidence count = candidate who measures their work.

3. INITIATIVE — did they PROPOSE and START things, or only respond to direction?
   Look for: "launched", "designed", "created from scratch", "identified", "pioneered".

4. PLATFORM SIGNALS — GitHub activity shows engineering output outside work hours.
   Score > 30 = visible engineering presence. Score 0 or unknown = neutral.
   Recruiter response rate < 20% may signal disinterest or unavailability.

5. LEADERSHIP FIT — see leadership expectation above.

EXPLICITLY IGNORE: technical skill names, company names, years of experience,
education institution. Those are other agents' responsibility.

CANDIDATES (behavioral signals only):
__CANDIDATES_BLOCK__

Respond ONLY with valid JSON, no markdown fences:
{
  "reviews": [
    {
      "candidate_id": "<id>",
      "score": <0-100>,
      "pros": ["<specific behavioral strength>", "..."],
      "cons": ["<specific behavioral gap>", "..."],
      "rationale": "<1-2 sentences on behavioral fit, citing ownership/impact evidence counts and specific language.>"
    }
  ]
}

Include ALL __N__ candidates.\
"""


def _behavioral_snippet(c: dict) -> str:
    profile = c.get("profile", {})
    sigs    = c.get("redrob_signals", {})
    intel   = c.get("intelligence_profile") or {}

    summary = profile.get("summary", "")[:400]

    # Ownership language snippets
    ownership_snippets = intel.get("ownership_signals", [])
    ownership_preview  = " | ".join(s[:150] for s in ownership_snippets[:3])

    # Impact snippets — this is behavioral evidence (they measure their work)
    impact_snippets = intel.get("impact_signals", [])
    impact_preview  = " | ".join(s[:150] for s in impact_snippets[:3])

    # Platform signals
    gh_score  = sigs.get("github_activity_score", -1)
    gh_str    = f"{gh_score:.0f}/100" if gh_score and gh_score > 0 else "not available"
    resp_rate = sigs.get("recruiter_response_rate", 0)
    otw       = "actively looking" if sigs.get("open_to_work_flag") else "passive"

    assessment_scores = sigs.get("skill_assessment_scores", {})
    assess_str = (
        ", ".join(f"{k}: {v:.0f}" for k, v in list(assessment_scores.items())[:4])
        if assessment_scores
        else "none taken"
    )

    why_selected = intel.get("why_selected", [])
    why_rejected = intel.get("why_rejected", [])

    return (
        f"[{c.get('candidate_id', '')}]\n"
        f"Self-summary: {summary}\n\n"
        f"OWNERSHIP SIGNALS ({intel.get('ownership_evidence', 0)} roles with builder language):\n"
        f"{ownership_preview or 'none extracted'}\n\n"
        f"IMPACT SIGNALS ({intel.get('impact_evidence', 0)} roles with quantified outcomes):\n"
        f"{impact_preview or 'none detected'}\n\n"
        f"Evidence verbs: built={intel.get('built_count',0)} shipped={intel.get('shipped_count',0)} "
        f"scaled={intel.get('scaled_count',0)} led={intel.get('led_count',0)} "
        f"→ ownership_score={intel.get('ownership_score',0)} impact_score={intel.get('impact_score',0)}\n"
        f"Leadership evidence: {intel.get('leadership_evidence', 0)} roles\n\n"
        f"GitHub score: {gh_str} | Job status: {otw} | "
        f"Recruiter response rate: {int(resp_rate * 100)}%\n"
        f"Skill assessments: {assess_str}\n\n"
        f"Pre-computed signals:\n"
        f"  Why strong: {'; '.join(why_selected[:3]) or 'none'}\n"
        f"  Gaps: {'; '.join(why_rejected[:2]) or 'none'}"
    )


def build_prompt(jd_signals: JDSignals, candidates: list[dict]) -> str:
    candidate_blob = "\n\n---\n\n".join(_behavioral_snippet(c) for c in candidates)

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__",      jd_signals.role_title)
    prompt = prompt.replace("__DOMAIN__",           jd_signals.domain)
    prompt = prompt.replace("__COMPANY_STAGE__",    jd_signals.company_stage)
    prompt = prompt.replace("__OWNERSHIP_LABEL__",  _ownership_label(jd_signals.ownership_weight))
    prompt = prompt.replace("__LEADERSHIP_LABEL__", _leadership_label(jd_signals.leadership_weight))
    prompt = prompt.replace("__RED_FLAGS__",         ", ".join(jd_signals.red_flags) or "none specified")
    prompt = prompt.replace("__CANDIDATES_BLOCK__", candidate_blob)
    prompt = prompt.replace("__N__",                str(len(candidates)))
    return prompt


def run_behavioral_specialist(
    jd_signals: JDSignals, candidates: list[dict]
) -> dict[str, AgentReviewResult]:
    if not candidates:
        return {}
    expected_ids = [str(c.get("candidate_id", "")) for c in candidates]
    prompt = build_prompt(jd_signals, candidates)
    return call_agent_batch(prompt, AGENT_NAME, expected_ids)