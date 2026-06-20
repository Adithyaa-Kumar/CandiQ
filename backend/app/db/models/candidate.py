"""
candidate.py
────────────
A candidate profile, ingested once and reused across many job evaluations.
The full structured profile (career history, skills, redrob signals) is
stored as JSON — it's heterogeneous by design (résumé-derived vs.
structured-import candidates have different shapes) and is always
read back into Python dicts by the pipeline, never queried by SQL directly.

The embedding vector itself lives in Qdrant; `qdrant_point_id` is the
foreign key tying this row to its vector.
"""

import uuid
from sqlalchemy import ForeignKey
from sqlalchemy import UniqueConstraint
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Original ingestion source id (e.g. "CAND_0000001" from a structured import)
    external_id: Mapped[str] = mapped_column(String(64), index=True, nullable=True)

    # Owning recruiter / account — candidates are scoped per-tenant
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    pool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_pools.id"),
        index=True,
        nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_title: Mapped[str] = mapped_column(String(255), nullable=True)
    years_of_experience: Mapped[float] = mapped_column(Float, nullable=True)

    # Full normalised candidate dict (profile, career_history, skills, education, redrob_signals)
    profile_data: Mapped[dict] = mapped_column(JSONB, nullable=False)

    intelligence_profile: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True
    )
    # Foreign key into the Qdrant collection (the point id used at upsert time)
    qdrant_point_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "pool_id",
            "external_id",
            name="uq_pool_candidate"
        ),
    )
