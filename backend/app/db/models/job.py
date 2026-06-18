"""
job.py
──────
An evaluation job: one JD submitted by a recruiter, processed through
Stage 1 (retrieval) → Stage 2 (specialist panel) → Stage 3 (arbitrator).

`status` and `current_stage` are updated by the Celery task as it
progresses, so the API can report live progress via polling.
"""

import enum
import uuid
from sqlalchemy import ForeignKey
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
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

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    candidate_pool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_pools.id"),
        nullable=False,
        index=True
    )
    jd_text: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="job_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=JobStatus.PENDING,
        nullable=False,
    )

    current_stage: Mapped[JobStage] = mapped_column(
        Enum(
            JobStage,
            name="job_stage",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=JobStage.QUEUED,
        nullable=False,
    )
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    status_message: Mapped[str] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # JDSignals snapshot — role_title, domain, skill_weights, etc. Stored so
    # results can be displayed with full context without re-deriving it.
    jd_signals: Mapped[dict] = mapped_column(JSONB, nullable=True)

    total_candidates: Mapped[int] = mapped_column(Integer, default=0)
    disqualified_count: Mapped[int] = mapped_column(Integer, default=0)
    shortlisted_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
