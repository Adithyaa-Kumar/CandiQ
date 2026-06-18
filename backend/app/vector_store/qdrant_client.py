"""
vector_store/qdrant_client.py
───────────────────────────────
Wraps Qdrant for candidate storage and hybrid retrieval.

Each candidate is stored ONCE (at ingest time) with a dense embedding
vector. Sparse (BM25-style) retrieval is computed on-demand at query
time over the candidate corpus already pulled back by the dense search
plus a keyword pre-filter — this avoids needing a second persistent
sparse index while still giving lexical matches a path into the
shortlist (see pipeline/retrieval.py for the union logic).

Collection is created once, idempotently, on first use.
"""

import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config import get_settings

settings = get_settings()

_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.qdrant_url)
        _ensure_collection(_client)
    return _client


def _ensure_collection(client: QdrantClient) -> None:
    collections = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection_name in collections:
        return

    client.create_collection(
        collection_name=settings.qdrant_collection_name,
        vectors_config=qmodels.VectorParams(
            size=384,  # all-MiniLM-L6-v2 output dimension
            distance=qmodels.Distance.COSINE,
        ),
    )


def upsert_candidate_vector(
    point_id: str,
    embedding: list[float],
    payload: dict,
) -> None:
    """
    Store/update a single candidate's embedding + lightweight payload.
    Payload carries only what's needed to filter/display at query time
    without a DB round-trip — full profile data stays in Postgres.
    """
    client = get_qdrant_client()
    client.upsert(
        collection_name=settings.qdrant_collection_name,
        points=[
            qmodels.PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload,
            )
        ],
    )


def upsert_candidate_vectors_batch(
    points: list[tuple[str, list[float], dict]],
) -> None:
    """Batch upsert — used by the ingest task for throughput."""
    client = get_qdrant_client()
    client.upsert(
        collection_name=settings.qdrant_collection_name,
        points=[
            qmodels.PointStruct(id=pid, vector=vec, payload=payload)
            for pid, vec, payload in points
        ],
    )


def dense_search(
    query_embedding: list[float],
    owner_id: uuid.UUID,
    limit: int = 200,
) -> list[dict]:
    """
    ANN cosine similarity search scoped to one recruiter's candidate pool.
    Returns [{id, score, payload}] sorted by descending similarity.
    """
    client = get_qdrant_client()
    results = client.search(
        collection_name=settings.qdrant_collection_name,
        query_vector=query_embedding,
        query_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="owner_id",
                    match=qmodels.MatchValue(value=str(owner_id)),
                )
            ]
        ),
        limit=limit,
    )
    return [
        {"id": r.id, "score": r.score, "payload": r.payload}
        for r in results
    ]


def delete_candidate_vector(point_id: str) -> None:
    client = get_qdrant_client()
    client.delete(
        collection_name=settings.qdrant_collection_name,
        points_selector=qmodels.PointIdsList(points=[point_id]),
    )


def count_candidates(owner_id: uuid.UUID) -> int:
    client = get_qdrant_client()
    result = client.count(
        collection_name=settings.qdrant_collection_name,
        count_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="owner_id",
                    match=qmodels.MatchValue(value=str(owner_id)),
                )
            ]
        ),
    )
    return result.count
