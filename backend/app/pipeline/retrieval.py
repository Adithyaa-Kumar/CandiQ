"""
pipeline/retrieval.py
────────────────────────
Stage 1: Strict Retrieval Filter.

Narrows the full candidate pool down to an adaptive shortlist BEFORE
the expensive multi-agent panel runs. This is the fix for the
30-minute-bottleneck problem: vector search is sub-second, and the
agent panel only ever sees a few hundred candidates at most, not
the full 100,000.

Safety design (why this doesn't lose top candidates)
──────────────────────────────────────────────────────
A single dense-embedding similarity ranking can misrank a genuinely
strong candidate who simply used different vocabulary than the JD.
So retrieval here is NOT "take the embedding top-K and discard the
rest." It is:

  1. Hard rule-based gate (score.py disqualifiers) — a boolean pass/fail,
     completely independent of any similarity ranking. This is the ONLY
     thing allowed to remove a candidate outright.
  2. Dense vector search (semantic) — ranks survivors of step 1 by
     cosine similarity to the JD embedding.
  3. Sparse keyword search (lexical) — ranks survivors of step 1 by
     exact skill/title term overlap with the JD, using BM25.
  4. Shortlist = UNION of top-N from (2) and top-N from (3), capped at
     an adaptive size. A candidate only needs to rank highly on EITHER
     signal to make it through — not both — so an embedding miss is
     recoverable via lexical match and vice versa.

Adaptive shortlist size
────────────────────────
  shortlist_size = clamp(
      ceil(shortlist_percentage * total_qualified),
      shortlist_min_size,
      shortlist_max_size,
  )

This avoids both failure modes of a flat percentage: too many
candidates reaching the expensive agent stage on a huge pool, and
too few surviving on a small pool.
"""

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
logger = get_logger(__name__)


def _build_jd_query_text(
    jd_text: str,
    signals: JDSignals
) -> str:

    skills = ", ".join(signals.skill_weights.keys())

    return f"""
Role: {signals.role_title}

Domain: {signals.domain}

Seniority: {signals.seniority}

Required Skills:
{skills}

Ideal Candidate:
{signals.ideal_candidate_summary}

Original JD:
{jd_text}
"""

def compute_shortlist_size(total_qualified: int) -> int:
    """Adaptive cap: never below shortlist_min_size, never above shortlist_max_size."""
    raw = math.ceil(settings.shortlist_percentage * total_qualified)
    return max(settings.shortlist_min_size, min(raw, settings.shortlist_max_size))


def run_retrieval_filter(
    jd_text: str,
    signals: JDSignals,
    candidates: list[dict],
    owner_id: uuid.UUID,
) -> dict:
    """
    Full Stage 1 pipeline. Returns a dict with:
      - shortlist: list of (candidate_dict, flags, rule_score, retrieval_score, retrieval_method)
      - disqualified: list of (candidate_dict, flags, rule_score)
      - total: int
      - shortlist_size: int (the adaptive cap actually used)
    """
    total = len(candidates)

    # ── Step 1: hard rule-based gate (independent of any ranking) ──────────
    qualified: list[tuple[dict, dict, dict]] = []   # (candidate, flags, rule_score)
    disqualified: list[tuple[dict, dict, dict]] = []

    for c in candidates:
        flags = get_career_flags(c, signals)
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
            "shortlist_size": 0,
        }

    shortlist_size = compute_shortlist_size(len(qualified))

    # If the qualified pool is already small enough, skip vector search
    # entirely — everyone who passed the rule gate goes straight through.
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

    # ── Step 2: dense vector search — Qdrant ANN lookup against vectors ────
    # already stored at ingest time. Nothing gets re-embedded here; this is
    # the actual fix for the 30-minute bottleneck the module docstring
    # above describes (previously this called embed_texts_batch() on every
    # qualified candidate, on every job run).
    jd_embedding = embed_text(_build_jd_query_text(jd_text, signals))

    qualified_ext_ids = {c.get("candidate_id") for c, _, _ in qualified}
    qdrant_hits = dense_search(jd_embedding, owner_id=owner_id, limit=total)

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
            hint="some candidates may predate the external_id payload field — re-ingest to backfill",
        )

    candidate_texts = [build_candidate_text(c) for c, _, _ in qualified]  # still needed for BM25 below
    dense_scores = [
        dense_score_by_ext_id.get(c.get("candidate_id"), 0.0) for c, _, _ in qualified
    ]
    dense_ranked = sorted(
        range(len(qualified)), key=lambda i: dense_scores[i], reverse=True
    )
    dense_top_n = set(dense_ranked[:shortlist_size])

    # ── Step 3: sparse BM25 lexical search ──────────────────────────────────
    tokenized_corpus = [_tokenize(t) for t in candidate_texts]
    bm25 = BM25Okapi(tokenized_corpus)
    query_tokens = _tokenize(_build_jd_query_text(jd_text, signals))
    sparse_scores = bm25.get_scores(query_tokens)
    sparse_ranked = sorted(
        range(len(qualified)), key=lambda i: sparse_scores[i], reverse=True
    )
    sparse_top_n = set(sparse_ranked[:shortlist_size])

    # ── Step 4: union, capped at shortlist_size by best combined rank ──────
    union_indices = dense_top_n | sparse_top_n

    def _retrieval_method(i: int) -> str:
        in_dense, in_sparse = i in dense_top_n, i in sparse_top_n
        if in_dense and in_sparse:
            return "both"
        return "dense" if in_dense else "sparse"

    # Normalise both score scales to 0-100 for a comparable combined score
    max_dense = max(dense_scores) or 1.0
    max_sparse = max(sparse_scores) or 1.0

    def _combined_score(i: int) -> float:
        d = (dense_scores[i] / max_dense) * 100
        s = (sparse_scores[i] / max_sparse) * 100
        # Best-of, not average — a candidate strong on either signal
        # shouldn't be punished for being weak on the other.
        return float(round(max(d, s), 2))

    union_sorted = sorted(union_indices, key=_combined_score, reverse=True)
    final_indices = union_sorted[:shortlist_size]

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
        "shortlist": shortlist,
        "disqualified": disqualified,
        "total": total,
        "shortlist_size": len(shortlist),
    }


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in text.replace(",", " ").replace("/", " ").split() if len(t) > 1]