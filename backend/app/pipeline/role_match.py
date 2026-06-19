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

    candidate_skills = {
        s.lower() for s in flags["skills"]
    }

    jd_skills = {
        s.lower() for s in signals.skill_weights.keys()
    }

    skill_overlap = len(candidate_skills & jd_skills)

    score += min(skill_overlap * 8, 40)

    return min(score, 100)