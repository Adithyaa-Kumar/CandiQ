"""
schemas/agent_review.py
─────────────────────────
Response model for a single specialist agent's review of a candidate.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.db.models.agent_review import AgentType


class AgentReviewResponse(BaseModel):
    id: uuid.UUID
    agent_type: AgentType
    score: float
    pros: list[str]
    cons: list[str]
    rationale: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
