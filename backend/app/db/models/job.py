"""
db/models/job.py
─────────────────
SQLAlchemy ORM model for evaluation jobs.

A Job ties a JD to a CandidatePool and tracks the full lifecycle:
pending → running → completed | failed, with per-stage progress.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStage(str, enum.Enum):
    QUEUED = "queued"
    ANALYZING_JD = "analyzing_jd"
    RETRIEVAL_FILTER = "retrieval_filter"
    SPECIALIST_PANEL = "specialist_panel"
    ARBITRATION = "arbitration"
    DONE = "done"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Owning recruiter
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)

    # The pool of candidates this job evaluates against
    candidate_pool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidate_pools.id"),
        index=True,
        nullable=False,
    )

    jd_text: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="job_status",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=JobStatus.PENDING,
        server_default="pending",
    )
    current_stage: Mapped[JobStage] = mapped_column(
        Enum(
            JobStage,
            name="job_stage",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=JobStage.QUEUED,
        server_default="queued",
    )

    progress_pct: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cached structured output from the JD analyzer
    jd_signals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Counters updated as the pipeline runs
    total_candidates: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    disqualified_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    shortlisted_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Cost / performance tracking
    llm_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    eval_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    results: Mapped[list["JobResult"]] = relationship(  # noqa: F821
        "JobResult", backref="job", cascade="all, delete-orphan", lazy="dynamic"
    )