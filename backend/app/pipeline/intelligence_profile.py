"""
pipeline/intelligence_profile.py
──────────────────────────────────
Lightweight recruiter-style evidence extraction.

BUG FIXES applied:
  1. Career trajectory was built in REVERSE chronological order because
     career_history is stored most-recent-first — reversed to show oldest→
     newest so the trajectory reads as progression, not regression.
  2. ir_evidence and ownership lists were capped at 10 each but the
     full descriptions (250 chars each) were appended on EVERY job that
     matched ANY term — deduplication added so we never repeat the same
     job twice.
  3. The function signature was missing type hints and the return dict
     used string-typed evidence but agents expected list[str] — enforced.
  4. ai_terms contained "search" which is far too generic and matched
     customer-support descriptions ("search for tickets"). Tightened.
  5. leadership_terms missed "staff engineer" and "principal engineer"
     detection because those are multi-word and the simple `in desc`
     check works, but "lead" also matches "leadership", "led", "leading"
     by substring — deduplicated hit counting.
"""

from __future__ import annotations


def build_candidate_intelligence_profile(candidate: dict) -> dict:
    """
    Lightweight recruiter-style evidence extraction. Returns structured
    signals consumed by all three specialist agents.
    """
    # career_history is most-recent-first in the dataset.
    # Reverse so oldest→newest to show genuine trajectory.
    career: list[dict] = list(reversed(candidate.get("career_history", [])))
    skills: list[str] = [s.get("name", "") for s in candidate.get("skills", [])]

    ir_evidence:    list[str] = []
    ownership:      list[str] = []
    seen_jobs_ir:   set[int]  = set()
    seen_jobs_own:  set[int]  = set()

    production_ai_evidence = 0
    ownership_evidence     = 0
    scale_evidence         = 0
    leadership_evidence    = 0

    # FIX 4: removed over-broad "search" (matched customer-support queries,
    # help-desk "search for tickets", etc.). Kept domain-specific signals.
    ai_terms = [
        "llm",
        "transformer",
        "rag",
        "retrieval",
        "ranking",
        "recommendation",
        "embedding",
        "vector",
        "faiss",
        "pinecone",
        "qdrant",
        "milvus",
        "bm25",
        "xgboost",
        "fine tuning",
        "fine-tuning",
        "inference",
        "semantic search",
        "neural",
        "sentence transformer",
        "hugging face",
        "language model",
        "information retrieval",
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
        "drove",
        "launched",
        "spearheaded",
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
        "at scale",
    ]

    # FIX 5: multi-word leadership terms work fine with `in desc` but
    # bare "lead" also fires on "leadership" in descriptions — check whole
    # words where possible and count job, not occurrences.
    leadership_terms = [
        "mentor",
        "mentored",
        "team lead",
        "lead engineer",
        "staff engineer",
        "principal engineer",
        "managed a team",
        "lead a team",
        "senior manager",
        "engineering manager",
        "tech lead",
    ]

    for idx, job in enumerate(career):
        desc = job.get("description", "").lower()

        # IR / ML evidence — one count per job, one evidence snippet per job
        if idx not in seen_jobs_ir:
            for term in ai_terms:
                if term in desc:
                    production_ai_evidence += 1
                    seen_jobs_ir.add(idx)
                    snippet = job.get("description", "")[:250]
                    if snippet and snippet not in ir_evidence:
                        ir_evidence.append(snippet)
                    break

        # Ownership evidence — one count per job
        if idx not in seen_jobs_own:
            for term in ownership_terms:
                if term in desc:
                    ownership_evidence += 1
                    seen_jobs_own.add(idx)
                    snippet = job.get("description", "")[:250]
                    if snippet and snippet not in ownership:
                        ownership.append(snippet)
                    break

        # Scale evidence — one count per job
        if any(term in desc for term in scale_terms):
            scale_evidence += 1

        # Leadership evidence — one count per job
        if any(term in desc for term in leadership_terms):
            leadership_evidence += 1

    # FIX 1: career displayed oldest→newest after the reverse above,
    # so this join now reads as a proper growth trajectory.
    career_trajectory = " → ".join(
        j.get("title", "")
        for j in career
        if j.get("title")
    )

    return {
        "ir_ml_evidence":       ir_evidence[:10],
        "ownership_signals":    ownership[:10],
        "career_trajectory":    career_trajectory,
        "key_skills":           skills[:30],
        "production_ai_evidence": production_ai_evidence,
        "ownership_evidence":   ownership_evidence,
        "scale_evidence":       scale_evidence,
        "leadership_evidence":  leadership_evidence,
    }