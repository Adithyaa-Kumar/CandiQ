def build_candidate_intelligence_profile(candidate: dict) -> dict:
    """
    Lightweight recruiter-style evidence extraction.
    """

    career = candidate.get("career_history", [])
    skills = [s.get("name", "") for s in candidate.get("skills", [])]

    ir_evidence = []
    ownership = []

    production_ai_evidence = 0
    ownership_evidence = 0
    scale_evidence = 0
    leadership_evidence = 0

    ai_terms = [
        "llm",
        "transformer",
        "rag",
        "retrieval",
        "ranking",
        "recommendation",
        "search",
        "embedding",
        "vector",
        "faiss",
        "pinecone",
        "qdrant",
        "milvus",
        "bm25",
        "xgboost",
        "fine tuning",
        "inference",
    ]

    ownership_terms = [
        "led",
        "owned",
        "built",
        "designed",
        "architected",
        "implemented",
        "created",
        "developed",
        "shipped",
        "responsible for",
    ]

    scale_terms = [
        "million",
        "millions",
        "100k",
        "1m",
        "10m",
        "high traffic",
        "high scale",
        "distributed",
        "real time",
        "large scale",
    ]

    leadership_terms = [
        "mentor",
        "mentored",
        "manager",
        "managed",
        "team lead",
        "lead engineer",
        "staff engineer",
        "principal engineer",
    ]

    for job in career:

        desc = job.get("description", "").lower()

        # IR / ML evidence
        for term in ai_terms:
            if term in desc:
                production_ai_evidence += 1
                ir_evidence.append(job.get("description", "")[:250])
                break

        # Ownership evidence
        for term in ownership_terms:
            if term in desc:
                ownership_evidence += 1
                ownership.append(job.get("description", "")[:250])
                break

        # Scale evidence
        for term in scale_terms:
            if term in desc:
                scale_evidence += 1
                break

        # Leadership evidence
        for term in leadership_terms:
            if term in desc:
                leadership_evidence += 1
                break

    return {
        "ir_ml_evidence": ir_evidence[:10],
        "ownership_signals": ownership[:10],

        "career_trajectory": " -> ".join(
            j.get("title", "")
            for j in career
        ),

        "key_skills": skills[:30],

        "production_ai_evidence": production_ai_evidence,
        "ownership_evidence": ownership_evidence,
        "scale_evidence": scale_evidence,
        "leadership_evidence": leadership_evidence,
    }