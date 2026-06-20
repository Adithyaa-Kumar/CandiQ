from app.pipeline.jd_analyzer import JDSignals


def compute_role_relevance(flags: dict, signals: JDSignals) -> float:
    """
    Dynamic role-fit score.
    Works for AI, Finance, HR, Sales, Marketing, Product, etc.
    """

    score = 0.0

    role_terms = set(
        signals.role_title.lower().replace("/", " ").split()
    )

    title_terms = set(
        flags["current_title"].lower().replace("/", " ").split()
    )

    title_overlap = len(role_terms & title_terms)
    score += min(title_overlap * 30, 60)

    candidate_skills = {s.lower() for s in flags["skills"]}
    jd_skills = {s.lower() for s in signals.skill_weights.keys()}

    # Fuzzy canonical match (substring either direction)
    skill_overlap = sum(
        1 for jd_s in jd_skills
        if any(jd_s in cs or cs in jd_s for cs in candidate_skills)
    )

    # Synonym match: check aliases for any JD skill not already matched
    matched_jd_skills = {
        jd_s for jd_s in jd_skills
        if any(jd_s in cs or cs in jd_s for cs in candidate_skills)
    }
    for canonical, aliases in signals.skill_synonyms.items():
        if canonical not in matched_jd_skills:
            if any(
                any(alias in cs or cs in alias for cs in candidate_skills)
                for alias in aliases
            ):
                skill_overlap += 1  # count synonym hit (no double-count; canonical was unmatched)

    # Career description scan: look for JD skill terms in work history text
    desc_text = " ".join(
        j.get("description", "").lower()
        for j in flags.get("raw", {}).get("career_history", [])
    )
    desc_hits = sum(
        1 for jd_s in jd_skills if jd_s in desc_text
    ) + sum(
        1 for aliases in signals.skill_synonyms.values()
        for alias in aliases if alias in desc_text
    )
    score += min(desc_hits * 5, 20)

    score += min(skill_overlap * 8, 40)

    return min(score, 100)