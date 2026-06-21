"""
schemas/candidate.py
─────────────────────
Request/response models for candidate ingestion.

CHANGE: Added pool_id to CandidateIngestResponse so the frontend
knows which pool was created and can poll its status specifically.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CandidateResponse(BaseModel):
    id: uuid.UUID
    external_id: str | None
    name: str
    current_title: str | None
    years_of_experience: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CandidateIngestResponse(BaseModel):
    """Returned immediately after upload — actual embedding happens async."""
    task_id: str
    candidates_received: int
    message: str
    pool_id: Optional[str] = None  # added: lets frontend poll pool status