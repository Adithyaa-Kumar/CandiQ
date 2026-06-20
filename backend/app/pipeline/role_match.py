"""
pipeline/role_match.py
─────────────────────────
Dynamic role-fit score. Works for AI, Finance, HR, Sales, Marketing,
Product, etc.

BUG FIXES applied:
  1. career description scan used `flags.get("raw", {})` but flags is
     built by get_career_flags() which always includes `"raw"` — however
     calling code might pass partial dicts during unit tests; made safe.
  2. Title overlap matched single-letter tokens from splitting on spaces
     (e.g. "AI" → ["AI"] but also "ML/AI" → ["ML", "AI", ""]) — filtered
     out tokens shorter than 3 chars to avoid spurious matches.
  3. Synonym scan double-counted: if a canonical skill matched directly
     AND its alias also appeared, the score incremented twice. Now aliases
     are only checked for skills NOT already matched canonically.
  4. desc_text hit count for skill terms was unbounded — one JD skill
     appearing 20× in one job description counted 20×. Capped per-skill.
  5. Scoring cap of 100 was applied but intermediate component caps
     weren't, so title_overlap=3 gave 90/100 leaving no headroom for the
     other signals. Rebalanced: title 40, skills 40, desc 20.
"""

from __future__ import annotations

from app.pipeline.jd_analyzer import JDSignals


def compute_role_relevance(flags: dict, signals: JDSignals) -> float:
    """
    Returns 0-100 role-fit score based on title alignment, skill overlap,
    and career description matches against JD signals.
    """
    score = 0.0

    # ── 1. Title overlap ───────────────────────────────────────────────────
    # FIX 5: rebalanced to 40 max for title (was 60), leaving more budget
    # for skills and description signals which are more reliable.
    # FIX 2: filter out tokens <3 chars (strips "", "a", "of", etc.)
    role_terms = {
        t for t in signals.role_title.lower().replace("/", " ").split()
        if len(t) >= 3
    }
    title_terms = {
        t for t in flags["current_title"].lower().replace("/", " ").split()
        if len(t) >= 3
    }
    title_overlap = len(role_terms & title_terms)
    score += min(title_overlap * 15, 40)   # rebalanced: was min(overlap*30, 60)

    # ── 2. Skill overlap ───────────────────────────────────────────────────
    candidate_skills = {s.lower() for s in flags["skills"]}
    jd_skills        = {s.lower() for s in signals.skill_weights.keys()}

    # Canonical direct match (substring either direction)
    matched_jd_skills: set[str] = set()
    for jd_s in jd_skills:
        if any(jd_s in cs or cs in jd_s for cs in candidate_skills):
            matched_jd_skills.add(jd_s)

    skill_overlap = len(matched_jd_skills)

    # FIX 3: synonym scan only for skills NOT already matched canonically
    for canonical, aliases in signals.skill_synonyms.items():
        if canonical.lower() not in matched_jd_skills:
            if any(
                any(alias in cs or cs in alias for cs in candidate_skills)
                for alias in aliases
            ):
                skill_overlap += 1

    score += min(skill_overlap * 8, 40)   # 40 max for skill signals

    # ── 3. Career description scan ─────────────────────────────────────────
    # FIX 1: safe access to raw career data
    career_jobs = flags.get("raw", {}).get("career_history", [])
    desc_text = " ".join(j.get("description", "").lower() for j in career_jobs)

    # FIX 4: count distinct JD skills that appear in the descriptions
    # (not total occurrences per skill — one appearance = one hit).
    desc_hits = sum(1 for jd_s in jd_skills if jd_s in desc_text)
    desc_hits += sum(
        1
        for aliases in signals.skill_synonyms.values()
        for alias in aliases
        if alias in desc_text
    )

    score += min(desc_hits * 5, 20)   # 20 max for description signals

    return min(score, 100.0)