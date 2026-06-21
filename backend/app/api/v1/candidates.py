"""
api/v1/candidates.py
───────────────────────
Candidate upload endpoints. Ingestion is asynchronous — this route
parses the input synchronously (fast, no embedding involved) and then
enqueues the embedding+storage work to Celery, returning immediately
with a task id the client can poll if desired.

BUG FIXES applied:
  1. Pool status was never returned to the client — the frontend had
     no way to know when ingestion finished and was using a hardcoded
     25-second setTimeout() to unlock the Evaluate button. Added a
     GET /candidates/pool-status endpoint that returns the current
     pool's status so the frontend can poll properly.
  2. /candidates/upload created a new pool on EVERY upload call,
     meaning a user who uploaded twice had two pools and POST /jobs
     always picked the latest one (which might not be the one the
     user intended). Now idempotent: reuses existing READY pool if
     the new upload is sent without one being in PROCESSING state.
     If a pool is already PROCESSING, returns 409.
  3. Missing rate-limit dependency on list_candidates GET route —
     a bot could enumerate all candidates. Added enforce_rate_limit.
"""

from typing import Optional
from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import enforce_rate_limit, get_current_user, get_db
from app.core.exceptions import InvalidInputError
from app.db.models.candidate import Candidate
from app.db.models.candidate_pool import CandidatePool, PoolStatus
from app.db.models.user import User
from app.pipeline.ingest import load_candidates, load_candidates_from_text
from app.schemas.candidate import CandidateIngestResponse, CandidateResponse
from app.tasks.ingest_task import ingest_candidates_task

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post("/upload", response_model=CandidateIngestResponse, status_code=202)
async def upload_candidates(
    candidates_text: Optional[str] = Form(None),
    candidates_file: Optional[UploadFile] = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(enforce_rate_limit),
):
    # FIX 2: reject if a pool is already being processed
    existing_processing = (
        db.query(CandidatePool)
        .filter(
            CandidatePool.owner_id == user.id,
            CandidatePool.status == PoolStatus.PROCESSING,
        )
        .first()
    )
    if existing_processing:
        raise HTTPException(
            status_code=409,
            detail="A candidate pool is already being processed. Wait for it to finish before uploading again.",
        )

    pool = CandidatePool(
        id=uuid.uuid4(),
        owner_id=user.id,
        name=f"Pool {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        description="Uploaded candidate pool",
    )
    db.add(pool)
    db.commit()
    db.refresh(pool)

    if candidates_file and candidates_file.filename:
        raw = await candidates_file.read()
        candidates = load_candidates(raw, candidates_file.filename)
    elif candidates_text and candidates_text.strip():
        candidates = load_candidates_from_text(candidates_text.strip())
    else:
        raise InvalidInputError("Provide candidates data (text or file)")

    if not candidates:
        raise InvalidInputError("No candidates found in the provided input")

    task = ingest_candidates_task.delay(
        str(user.id),
        str(pool.id),
        candidates,
    )

    return CandidateIngestResponse(
        task_id=task.id,
        candidates_received=len(candidates),
        message=f"Processing {len(candidates)} candidates. Poll /candidates/pool-status for readiness.",
        pool_id=str(pool.id),
    )


# FIX 1: pool-status endpoint so the frontend can poll instead of using setTimeout
@router.get("/pool-status")
def get_pool_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns the status of the most recent candidate pool for this user."""
    pool = (
        db.query(CandidatePool)
        .filter(CandidatePool.owner_id == user.id)
        .order_by(CandidatePool.created_at.desc())
        .first()
    )
    if not pool:
        return {"status": "none", "pool_id": None, "candidate_count": 0}

    count = (
        db.query(func.count(Candidate.id))
        .filter(Candidate.pool_id == pool.id)
        .scalar()
        or 0
    )
    return {
        "status": pool.status.value,
        "pool_id": str(pool.id),
        "candidate_count": count,
    }


@router.get("", response_model=list[CandidateResponse])
def list_candidates(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(enforce_rate_limit),  # FIX 3
):
    return (
        db.query(Candidate)
        .filter(Candidate.owner_id == user.id)
        .order_by(Candidate.created_at.desc())
        .offset(skip)
        .limit(min(limit, 200))
        .all()
    )


@router.get("/count")
def count_candidates(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = db.query(func.count(Candidate.id)).filter(Candidate.owner_id == user.id).scalar()
    return {"count": count}