"""
job_result.py
─────────────
One row per candidate that made it into a job's shortlist (Stage 1
survivors). Disqualified candidates are NOT given a row here — they're
summarised as a count on the Job itself, since per-candidate detail
for thousands of rejects isn't useful to a recruiter.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class JobResult(Base):
    __tablename__ = "job_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), index=True, nullable=False)

    # Denormalised for fast display without a join
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_title: Mapped[str] = mapped_column(String(255), nullable=True)

    # Stage 1 retrieval signal (before agents ever see the candidate)
    retrieval_score: Mapped[float] = mapped_column(Float, nullable=True)
    retrieval_method: Mapped[str] = mapped_column(String(20), nullable=True)  # "dense" | "sparse" | "both"

    # Rule-based score (score.py composite, pre-agent)
    rule_composite_score: Mapped[float] = mapped_column(Float, nullable=True)

    # Final consensus output from the Arbitrator (Stage 3)
    consensus_score: Mapped[float] = mapped_column(Float, nullable=True)
    final_rank: Mapped[int] = mapped_column(Integer, nullable=True)
    executive_summary: Mapped[str] = mapped_column(Text, nullable=True)

    is_disqualified: Mapped[bool] = mapped_column(Boolean, default=False)
    disqualify_reason: Mapped[str] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    agent_reviews: Mapped[list["AgentReview"]] = relationship(
        "AgentReview", backref="job_result", cascade="all, delete-orphan", lazy="selectin"
    )
