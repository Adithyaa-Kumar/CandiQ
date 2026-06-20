"""
pipeline/retrieval.py
────────────────────────
Stage 1: Strict Retrieval Filter.

Narrows the full candidate pool down to an adaptive shortlist BEFORE
the expensive multi-agent panel runs.

Safety design:
  1. Hard rule-based gate (score.py disqualifiers) — boolean pass/fail.
  2. Dense vector search (semantic) — cosine similarity to JD embedding.
  3. Sparse keyword search (lexical) — BM25 over candidate text.
  4. Shortlist = UNION of top-N from (2) and top-N from (3), capped.

BUG FIXES applied:
  1. Qdrant dense_search was called with limit=total (entire pool size)
     but the Qdrant client's default search limit is 10 — if the caller
     doesn't explicitly set `with_payload=True` in its PointsSelector,
     payloads come back empty. Fixed by ensuring we always get payloads
     (handled in qdrant_client.py) and using the actual total as limit.
  2. _combined_score() used best-of (max(dense, sparse)) rather than
     a weighted blend — a candidate who scored 100 on sparse but 0 on
     dense (exact keyword match, no semantic understanding) would appear
     first. Changed to a blended score: 0.6*dense + 0.4*sparse for
     fairer reranking, with normalisation to 0-100.
  3. tokenizer split on spaces only — "machine-learning" and
     "machine learning" tokenized differently. Added hyphen split.
  4. JD query text builder included the full jd_text which could be very
     long (multi-page PDFs) and dominated the embedding, washing out the
     structured signals (skills, ideal candidate). Capped raw JD to 1500
     chars and moved it after the structured fields.
  5. When all candidates are disqualified, the function returned
     {"shortlist": [], ...} but the evaluate_task expected the key
     "shortlist_size" too — always present now.
"""

from __future__ import annotations

import math
import uuid

from rank_bm25 import BM25Okapi

from app.config import get_settings
from app.pipeline.embed import embed_text
from app.pipeline.jd_analyzer import JDSignals
from app.pipeline.parse_candidates import build_candidate_text, get_career_flags
from app.pipeline.score import score_candidate
from app.vector_store.qdrant_client import dense_search
from app.logging_conf import get_logger

settings = get_settings()
logger   = get_logger(__name__)


def _build_jd_query_text(jd_text: str, signals: JDSignals) -> str:
    # FIX 4: structured fields first, then truncated raw JD
    skills = ", ".join(signals.skill_weights.keys())
    return (
        f"Role: {signals.role_title}\n"
        f"Domain: {signals.domain}\n"
        f"Seniority: {signals.seniority}\n"
        f"Required Skills:\n{skills}\n\n"
        f"Ideal Candidate:\n{signals.ideal_candidate_summary}\n\n"
        f"Original JD (excerpt):\n{jd_text[:1500]}"
    )


def compute_shortlist_size(total_qualified: int) -> int:
    raw = math.ceil(settings.shortlist_percentage * total_qualified)
    return max(settings.shortlist_min_size, min(raw, settings.shortlist_max_size))


def run_retrieval_filter(
    jd_text: str,
    signals: JDSignals,
    candidates: list[dict],
    owner_id: uuid.UUID,
) -> dict:
    total = len(candidates)

    # ── Step 1: rule-based gate ──────────────────────────────────────────
    qualified:    list[tuple[dict, dict, dict]] = []
    disqualified: list[tuple[dict, dict, dict]] = []

    for c in candidates:
        flags      = get_career_flags(c, signals)
        rule_score = score_candidate(flags, signals)
        if rule_score["disqualified"]:
            disqualified.append((c, flags, rule_score))
        else:
            qualified.append((c, flags, rule_score))

    if not qualified:
        return {
            "shortlist": [],
            "disqualified": disqualified,
            "total": total,
            "shortlist_size": 0,          # FIX 5
        }

    shortlist_size = compute_shortlist_size(len(qualified))

    # If the qualified pool is small enough, skip vector search
    if len(qualified) <= shortlist_size:
        shortlist = [
            (c, flags, rule_score, rule_score["composite_score"], "rule_gate_only")
            for c, flags, rule_score in qualified
        ]
        logger.info(
            "retrieval.skip_vector_search",
            qualified=len(qualified), shortlist_size=shortlist_size,
        )
        return {
            "shortlist": shortlist,
            "disqualified": disqualified,
            "total": total,
            "shortlist_size": len(shortlist),
        }

    # ── Step 2: dense vector search ──────────────────────────────────────
    jd_embedding = embed_text(_build_jd_query_text(jd_text, signals))

    qualified_ext_ids = {c.get("candidate_id") for c, _, _ in qualified}
    # FIX 1: pass explicit large limit to get enough Qdrant results
    qdrant_hits = dense_search(jd_embedding, owner_id=owner_id, limit=max(total, 2000))

    dense_score_by_ext_id = {
        hit["payload"].get("external_id"): hit["score"]
        for hit in qdrant_hits
        if hit["payload"].get("external_id") in qualified_ext_ids
    }

    if len(dense_score_by_ext_id) < len(qualified):
        logger.warning(
            "retrieval.qdrant_coverage_gap",
            qualified=len(qualified),
            qdrant_matches=len(dense_score_by_ext_id),
        )

    dense_scores = [
        dense_score_by_ext_id.get(c.get("candidate_id"), 0.0) for c, _, _ in qualified
    ]

    # ── Step 3: BM25 lexical search ─────────────────────────────────────
    candidate_texts   = [build_candidate_text(c) for c, _, _ in qualified]
    # FIX 3: also split on hyphens for compound terms
    tokenized_corpus  = [_tokenize(t) for t in candidate_texts]
    bm25              = BM25Okapi(tokenized_corpus)
    query_tokens      = _tokenize(_build_jd_query_text(jd_text, signals))
    sparse_scores_raw = bm25.get_scores(query_tokens)

    # ── Step 4: blended union shortlist ─────────────────────────────────
    max_dense  = max(dense_scores)       if max(dense_scores) > 0  else 1.0
    max_sparse = max(sparse_scores_raw)  if max(sparse_scores_raw) > 0 else 1.0

    # FIX 2: 60/40 blend instead of pure best-of
    def _combined_score(i: int) -> float:
        d = (dense_scores[i]    / max_dense)  * 100.0
        s = (sparse_scores_raw[i] / max_sparse) * 100.0
        return round(0.60 * d + 0.40 * s, 2)

    dense_ranked  = sorted(range(len(qualified)), key=lambda i: dense_scores[i],     reverse=True)
    sparse_ranked = sorted(range(len(qualified)), key=lambda i: sparse_scores_raw[i], reverse=True)

    dense_top_n  = set(dense_ranked[:shortlist_size])
    sparse_top_n = set(sparse_ranked[:shortlist_size])
    union_indices = dense_top_n | sparse_top_n

    def _retrieval_method(i: int) -> str:
        in_dense, in_sparse = i in dense_top_n, i in sparse_top_n
        if in_dense and in_sparse:
            return "both"
        return "dense" if in_dense else "sparse"

    union_sorted    = sorted(union_indices, key=_combined_score, reverse=True)
    final_indices   = union_sorted[:shortlist_size]

    shortlist = [
        (
            qualified[i][0],
            qualified[i][1],
            qualified[i][2],
            _combined_score(i),
            _retrieval_method(i),
        )
        for i in final_indices
    ]

    logger.info(
        "retrieval.complete",
        total=total,
        qualified=len(qualified),
        dense_candidates=len(dense_top_n),
        sparse_candidates=len(sparse_top_n),
        union_size=len(union_indices),
        final_shortlist=len(shortlist),
    )

    return {
        "shortlist":      shortlist,
        "disqualified":   disqualified,
        "total":          total,
        "shortlist_size": len(shortlist),
    }


def _tokenize(text: str) -> list[str]:
    # FIX 3: split on commas, slashes, AND hyphens for compound terms
    for ch in (",", "/", "-"):
        text = text.replace(ch, " ")
    return [t.lower() for t in text.split() if len(t) > 1]