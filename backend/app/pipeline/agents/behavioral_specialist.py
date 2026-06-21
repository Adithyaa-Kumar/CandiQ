"""
pipeline/agents/behavioral_specialist.py
────────────────────────────────────────────
Agent 3: Behavioral & Platform Signal Specialist.

Focus: open-source activity, communication clarity in profile text,
ownership and initiative signals from role descriptions, and
soft-skill indicators detectable from the profile.

BUG FIXES applied:
  1. Same oversized prompt problem — raw evidence blocks removed.
  2. Prompt asked the agent to judge "communication clarity" but gave it
     a structured profile blob that's already been formatted — agents
     can't distinguish good writing from Claude's formatting. Changed the
     instruction to assess the CONTENT specificity (concrete numbers,
     named systems, measurable outcomes) rather than prose quality.
  3. Ownership and leadership weights sent as raw floats (same issue as
     trajectory_specialist) — changed to descriptive labels.
  4. The agent was told to "EXPLICITLY IGNORE: technical skill depth,
     company pedigree, years of experience" but then its candidate block
     contained all of those. Agents would always drift into scoring them.
     Behavioral block now strips roles/titles and shows ONLY behavioral
     signals: summary description quality, GitHub score, assessment scores,
     and the intelligence-profile ownership/leadership counts.
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
1. Specificity of self-description: do they describe CONCRETE work with measurable
   outcomes ("reduced latency by 40%", "owned the ranker from scratch to 12% revenue lift")
   or vague buzzwords ("worked on AI solutions", "contributed to the team")?
   Concrete descriptions score higher — they indicate genuine ownership of the work.

2. Initiative signals: do descriptions show they PROPOSED and STARTED things, or
   only responded to direction? Count "led", "designed", "launched", "created from scratch"
   vs "contributed to", "helped with", "assisted in".

3. GitHub / open-source activity (if available): active score >30 = visible engineering
   output outside work hours. Score 0 or unknown = neutral, not negative.

4. Platform engagement: high recruiter response rate signals they're professionally
   engaged. Very low rate (< 20%) may indicate unavailability or disinterest.

5. Ownership fit: see expectation above.

6. Leadership fit: see expectation above.

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
      "pros": ["<short phrase>", "..."],
      "cons": ["<short phrase>", "..."],
      "rationale": "<1-2 sentences on behavioral fit, citing specific evidence>"
    }
  ]
}

Include ALL __N__ candidates.\
"""


def _behavioral_snippet(c: dict) -> str:
    """
    FIX 4: produce a behavioral-only block — no role titles, company names,
    or skill lists that would anchor the behavioral agent on non-behavioral signals.
    """
    profile = c.get("profile", {})
    sigs    = c.get("redrob_signals", {})
    intel   = c.get("intelligence_profile") or {}

    summary = profile.get("summary", "")[:400]

    # Behavioral evidence from work descriptions
    ownership_snippets  = intel.get("ownership_signals", [])
    ownership_preview   = " | ".join(s[:120] for s in ownership_snippets[:3])

    # Platform signals
    gh_score    = sigs.get("github_activity_score", -1)
    gh_str      = f"{gh_score:.0f}/100" if gh_score and gh_score > 0 else "not available"
    resp_rate   = sigs.get("recruiter_response_rate", 0)
    otw         = "actively looking" if sigs.get("open_to_work_flag") else "passive"

    assessment_scores = sigs.get("skill_assessment_scores", {})
    assess_str = (
        ", ".join(f"{k}: {v:.0f}" for k, v in list(assessment_scores.items())[:4])
        if assessment_scores
        else "none taken"
    )

    return (
        f"[{c.get('candidate_id', '')}]\n"
        f"Self-summary: {summary}\n"
        f"Ownership evidence count: {intel.get('ownership_evidence', 0)} | "
        f"Leadership evidence count: {intel.get('leadership_evidence', 0)}\n"
        f"Evidence verbs: built={intel.get('built_count', 0)} shipped={intel.get('shipped_count', 0)} "
        f"scaled={intel.get('scaled_count', 0)} led={intel.get('led_count', 0)} "
        f"→ evidence_score={intel.get('evidence_score', 0)}\n"
        f"Sample ownership language: {ownership_preview or 'none extracted'}\n"
        f"GitHub score: {gh_str} | Job status: {otw} | "
        f"Recruiter response rate: {int(resp_rate * 100)}%\n"
        f"Skill assessments taken: {assess_str}"
    )


def build_prompt(jd_signals: JDSignals, candidates: list[dict]) -> str:
    candidate_blob = "\n\n---\n\n".join(_behavioral_snippet(c) for c in candidates)

    prompt = _PROMPT_TEMPLATE
    prompt = prompt.replace("__ROLE_TITLE__",       jd_signals.role_title)
    prompt = prompt.replace("__DOMAIN__",            jd_signals.domain)
    prompt = prompt.replace("__COMPANY_STAGE__",     jd_signals.company_stage)
    prompt = prompt.replace("__OWNERSHIP_LABEL__",   _ownership_label(jd_signals.ownership_weight))
    prompt = prompt.replace("__LEADERSHIP_LABEL__",  _leadership_label(jd_signals.leadership_weight))
    prompt = prompt.replace("__RED_FLAGS__",          ", ".join(jd_signals.red_flags) or "none specified")
    prompt = prompt.replace("__CANDIDATES_BLOCK__",  candidate_blob)
    prompt = prompt.replace("__N__",                 str(len(candidates)))
    return prompt


def run_behavioral_specialist(
    jd_signals: JDSignals, candidates: list[dict]
) -> dict[str, AgentReviewResult]:
    if not candidates:
        return {}
    expected_ids = [str(c.get("candidate_id", "")) for c in candidates]
    prompt = build_prompt(jd_signals, candidates)
    return call_agent_batch(prompt, AGENT_NAME, expected_ids)