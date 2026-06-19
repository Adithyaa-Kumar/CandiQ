"""
api/v1/jobs.py
─────────────────
The evaluation job lifecycle:
  POST /jobs               — submit a JD, enqueue the evaluation, return job_id immediately
  GET  /jobs/{id}           — poll status/progress (used by the frontend polling hook)
  GET  /jobs/{id}/results   — fetch final ranked results once status == completed
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session, selectinload

from app.api.deps import enforce_rate_limit, get_current_user, get_db
from app.core.exceptions import InvalidInputError, NotFoundError
from app.db.models.job import Job, JobStatus
from app.db.models.job_result import JobResult
from app.db.models.user import User
from app.schemas.job import (
    JDSignalsResponse,
    JobCreateResponse,
    JobResultItem,
    JobResultsResponse,
    JobStatusResponse,
)
from app.tasks.evaluate_task import evaluate_job_task

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobCreateResponse, status_code=202)
async def create_job(
    jd_text: Optional[str] = Form(None),
    jd_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(enforce_rate_limit),
):
    from app.db.models.candidate_pool import CandidatePool
    pool = (
        db.query(CandidatePool)
        .filter(CandidatePool.owner_id == user.id)
        .order_by(CandidatePool.created_at.desc())
        .first()
    )

    if not pool:
        raise InvalidInputError(
            "No candidate pool found. Upload candidates first."
        )
    if jd_file and jd_file.filename:
        raw = await jd_file.read()
        jd = _extract_jd_text(raw, jd_file.filename)
    elif jd_text and jd_text.strip():
        jd = jd_text.strip()
    else:
        raise InvalidInputError("Provide a job description (text or file)")

    if len(jd) < 30:
        raise InvalidInputError("Job description is too short to analyze")

    job = Job(
        id=uuid.uuid4(),
        owner_id=user.id,
        candidate_pool_id=pool.id,
        jd_text=jd,
        status=JobStatus.PENDING,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    evaluate_job_task.delay(str(job.id))

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        message="Evaluation queued. Poll GET /jobs/{job_id} for progress.",
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(Job, job_id)
    if not job or job.owner_id != user.id:
        raise NotFoundError("Job not found")

    jd_signals_resp = None
    if job.jd_signals:
        top_skills = sorted(
            job.jd_signals.get("skill_weights", {}).items(), key=lambda x: -x[1]
        )[:10]
        jd_signals_resp = JDSignalsResponse(
            role_title=job.jd_signals.get("role_title", ""),
            domain=job.jd_signals.get("domain", ""),
            seniority=job.jd_signals.get("seniority", ""),
            exp_min=job.jd_signals.get("exp_min", 0),
            exp_max=job.jd_signals.get("exp_max", 0),
            top_skills=top_skills,
        )

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        current_stage=job.current_stage,
        progress_pct=job.progress_pct,
        status_message=job.status_message,
        error_message=job.error_message,
        jd_signals=jd_signals_resp,
        total_candidates=job.total_candidates,
        disqualified_count=job.disqualified_count,
        shortlisted_count=job.shortlisted_count,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.get("/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(
    job_id: uuid.UUID,
    include_disqualified: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(Job, job_id)
    if not job or job.owner_id != user.id:
        raise NotFoundError("Job not found")

    query = (
        db.query(JobResult)
        .options(selectinload(JobResult.agent_reviews))
        .filter(JobResult.job_id == job.id)
    )
    if not include_disqualified:
        query = query.filter(JobResult.is_disqualified.is_(False))

    rows = query.order_by(JobResult.final_rank.asc().nullslast()).all()

    role_title = job.jd_signals.get("role_title") if job.jd_signals else None

    results = [
        JobResultItem(
            candidate_id=r.candidate_id,
            candidate_name=r.candidate_name,
            current_title=r.current_title,
            retrieval_score=r.retrieval_score,
            retrieval_method=r.retrieval_method,
            rule_composite_score=r.rule_composite_score,
            consensus_score=r.consensus_score,
            final_rank=r.final_rank,
            strengths=r.strengths or [],
            risks=r.risks or [],
            alternatives=r.alternatives or [],
            agent_reviews=r.agent_reviews,
        )
        for r in rows
    ]

    return JobResultsResponse(
        job_id=job.id,
        status=job.status,
        role_title=role_title,
        total_candidates=job.total_candidates,
        disqualified_count=job.disqualified_count,
        shortlisted_count=job.shortlisted_count,
        results=results,
    )


def _extract_jd_text(raw: bytes, filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".docx"):
        try:
            import io

            import docx
            doc = docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception:
            return raw.decode("utf-8", errors="replace")
    if lower.endswith(".pdf"):
        try:
            import io

            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(raw))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return raw.decode("utf-8", errors="replace")
    return raw.decode("utf-8", errors="replace")