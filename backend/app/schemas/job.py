"""
schemas/job.py
───────────────
Request/response models for the evaluation job lifecycle.

BUG FIX: JobResultItem previously had `executive_summary` (old field name)
instead of `strengths`, `risks`, `alternatives` — mismatched the DB model
since migration d4c1611d96eb, causing the frontend to render blank results.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.db.models.job import JobStage, JobStatus
from app.schemas.agent_review import AgentReviewResponse


class JobCreateResponse(BaseModel):
    job_id: uuid.UUID
    status: JobStatus
    message: str


class JDSignalsResponse(BaseModel):
    role_title: str
    domain: str
    seniority: str
    exp_min: int
    exp_max: int
    top_skills: list[tuple[str, int]] = Field(default_factory=list)


class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    status: JobStatus
    current_stage: JobStage
    progress_pct: int
    status_message: str | None
    error_message: str | None
    jd_signals: JDSignalsResponse | None
    total_candidates: int
    disqualified_count: int
    shortlisted_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    # Cost / performance metadata
    llm_calls: int = 0
    eval_time_seconds: float | None = None

    model_config = {"from_attributes": True}


class JobResultItem(BaseModel):
    candidate_id: uuid.UUID
    candidate_name: str
    current_title: str | None
    retrieval_score: float | None
    retrieval_method: str | None
    rule_composite_score: float | None
    consensus_score: float | None
    final_rank: int | None
    # FIX: was `executive_summary: str | None` — renamed columns since migration d4c1611d96eb
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    is_disqualified: bool = False
    disqualify_reason: Optional[str] = None
    agent_reviews: list[AgentReviewResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class JobResultsResponse(BaseModel):
    job_id: uuid.UUID
    status: JobStatus
    role_title: str | None
    total_candidates: int
    disqualified_count: int
    shortlisted_count: int
    results: list[JobResultItem]