"""
models/__init__.py
───────────────────
Importing every model here ensures Alembic's `target_metadata = Base.metadata`
autogenerate picks up the full schema, regardless of which module
triggers the import first.
"""

from app.db.models.agent_review import AgentReview, AgentType
from app.db.models.candidate import Candidate
from app.db.models.job import Job, JobStage, JobStatus
from app.db.models.job_result import JobResult
from app.db.models.user import User
from app.db.models.candidate_pool import CandidatePool

__all__ = [
    "User",
    "Candidate",
    "Job",
    "JobStatus",
    "JobStage",
    "JobResult",
    "AgentReview",
    "AgentType",
]
