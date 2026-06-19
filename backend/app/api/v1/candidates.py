"""
api/v1/candidates.py
───────────────────────
Candidate upload endpoints. Ingestion is asynchronous — this route
parses the input synchronously (fast, no embedding involved) and then
enqueues the embedding+storage work to Celery, returning immediately
with a task id the client can poll if desired.
"""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import enforce_rate_limit, get_current_user, get_db
from app.core.exceptions import InvalidInputError
from app.db.models.candidate import Candidate
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
    from app.db.models.candidate_pool import CandidatePool
    import uuid

    pool = CandidatePool(
        id=uuid.uuid4(),
        owner_id=user.id,
        name=f"Pool {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
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
        message=f"Processing {len(candidates)} candidates.",
    )

@router.get("", response_model=list[CandidateResponse])
def list_candidates(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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