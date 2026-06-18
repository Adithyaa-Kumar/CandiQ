"""
agent_review.py
────────────────
Individual specialist agent reviews (Tech, Trajectory, Behavioral) for
a single candidate within a job. This is what makes the system
explainable — the UI's "Agent Review Drawer" reads directly from here
rather than from a single opaque score.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class AgentType(str, enum.Enum):
    TECH_SPECIALIST = "tech_specialist"
    TRAJECTORY_SPECIALIST = "trajectory_specialist"
    BEHAVIORAL_SPECIALIST = "behavioral_specialist"


class AgentReview(Base):
    __tablename__ = "agent_reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    job_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_results.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    agent_type: Mapped[AgentType] = mapped_column(
        Enum(
            AgentType,
            values_callable=lambda e: [x.value for x in e],
            name="agent_type",
        ),
        nullable=False,
    )

    score: Mapped[float] = mapped_column(Float, nullable=False)   # ← ADD THIS

    pros: Mapped[list] = mapped_column(JSONB, default=list)
    cons: Mapped[list] = mapped_column(JSONB, default=list)
    rationale: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )