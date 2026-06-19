import uuid
import enum
from sqlalchemy import Enum
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

class PoolStatus(str, enum.Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    
class CandidatePool(Base):
    __tablename__ = "candidate_pools"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        index=True,
        nullable=False
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    description: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    
    status: Mapped[PoolStatus] = mapped_column(
        Enum(
            PoolStatus,
            name="pool_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=PoolStatus.PROCESSING,
        server_default="processing",
    )