"""
tasks/ingest_task.py
───────────────────────
Background task that processes a batch of candidates ONCE: normalises
them, embeds them, and stores them in both Postgres (full profile,
queryable) and Qdrant (vector, for fast retrieval). This is the task
that replaces "re-embed everything on every JD submission."
"""

import uuid

from app.celery_app import celery_app
from app.db.models.candidate import Candidate
from app.db.session import SessionLocal
from app.logging_conf import get_logger
from app.pipeline.embed import embed_texts_batch
from app.pipeline.parse_candidates import build_candidate_text
from app.vector_store.qdrant_client import upsert_candidate_vectors_batch
from app.db.models.candidate_pool import CandidatePool, PoolStatus
from app.pipeline.intelligence_profile import (
    build_candidate_intelligence_profile
)

logger = get_logger(__name__)

EMBED_BATCH_SIZE = 64


@celery_app.task(name="ingest_candidates", bind=True)
def ingest_candidates_task(self, owner_id: str, pool_id: str, candidates: list[dict]) -> dict:
    db = SessionLocal()
    owner_uuid = uuid.UUID(owner_id)
    pool_uuid = uuid.UUID(pool_id)

    pool = db.get(CandidatePool, pool_uuid)

    if pool:
        pool.status = PoolStatus.PROCESSING
        db.commit()

    inserted = 0
    errors = 0

    try:
        texts = [build_candidate_text(c) for c in candidates]

        # Embed in sub-batches to bound memory use on very large uploads
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch_texts = texts[i : i + EMBED_BATCH_SIZE]
            all_embeddings.extend(embed_texts_batch(batch_texts))
            self.update_state(
                state="PROGRESS",
                meta={"current": i + len(batch_texts), "total": len(candidates)},
            )

        qdrant_points: list[tuple[str, list[float], dict]] = []

        for c, embedding in zip(candidates, all_embeddings):
            try:
                profile = c.get("profile", {})
                point_id = str(uuid.uuid4())

                candidate_row = Candidate(
                    id=uuid.uuid4(),
                    external_id=c.get("candidate_id"),
                    owner_id=owner_uuid,
                    pool_id=pool_uuid,
                    name=profile.get("anonymized_name", "Unknown"),
                    current_title=profile.get("current_title", ""),
                    years_of_experience=profile.get("years_of_experience", 0),
                    profile_data=c,
                    qdrant_point_id=point_id,
                    intelligence_profile=build_candidate_intelligence_profile(c),
                )
                db.add(candidate_row)

                qdrant_points.append((
                    point_id,
                    embedding,
                    {
                        "owner_id": str(owner_uuid),
                        "candidate_db_id": str(candidate_row.id),
                        "external_id": c.get("candidate_id"),
                        "name": profile.get("anonymized_name", "Unknown"),
                        "current_title": profile.get("current_title", ""),
                    },
                ))
                inserted += 1
            except Exception as e:
                logger.error("ingest_candidate_failed", error=str(e))
                errors += 1

        db.commit()

        # Batch upsert to Qdrant after the DB commit succeeds, so a Qdrant
        # failure never leaves orphaned vector points referencing nothing.
        if qdrant_points:
            upsert_candidate_vectors_batch(qdrant_points)

        pool = db.get(CandidatePool, pool_uuid)
        if pool:
            pool.status = PoolStatus.READY

        db.commit()
        return {"inserted": inserted, "errors": errors, "total": len(candidates)}

    except Exception as e:
        db.rollback()

        pool = db.get(CandidatePool, pool_uuid)
        if pool:
            pool.status = PoolStatus.FAILED
            db.commit()

        logger.error("ingest_task_failed", owner_id=owner_id, error=str(e))
        raise
    finally:
        db.close()
        
    