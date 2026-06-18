"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── candidates ─────────────────────────────────────────────────────────
    op.create_table(
        "candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", sa.String(64), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("current_title", sa.String(255), nullable=True),
        sa.Column("years_of_experience", sa.Float(), nullable=True),
        sa.Column("profile_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("qdrant_point_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_candidates_external_id", "candidates", ["external_id"])
    op.create_index("ix_candidates_owner_id", "candidates", ["owner_id"])
    op.create_index("ix_candidates_owner_external", "candidates", ["owner_id", "external_id"])
    op.create_unique_constraint("uq_candidates_qdrant_point_id", "candidates", ["qdrant_point_id"])

    # ── jobs ───────────────────────────────────────────────────────────────
    job_status_enum = postgresql.ENUM(
        "pending", "running", "completed", "failed", name="job_status"
    )
    job_stage_enum = postgresql.ENUM(
        "queued", "analyzing_jd", "retrieval_filter", "specialist_panel",
        "arbitration", "done", name="job_stage",
    )

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("status", job_status_enum, nullable=False, server_default="pending"),
        sa.Column("current_stage", job_stage_enum, nullable=False, server_default="queued"),
        sa.Column("progress_pct", sa.Integer(), server_default="0"),
        sa.Column("status_message", sa.String(500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("jd_signals", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("total_candidates", sa.Integer(), server_default="0"),
        sa.Column("disqualified_count", sa.Integer(), server_default="0"),
        sa.Column("shortlisted_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_owner_id", "jobs", ["owner_id"])

    # ── job_results ────────────────────────────────────────────────────────
    op.create_table(
        "job_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_name", sa.String(255), nullable=False),
        sa.Column("current_title", sa.String(255), nullable=True),
        sa.Column("retrieval_score", sa.Float(), nullable=True),
        sa.Column("retrieval_method", sa.String(20), nullable=True),
        sa.Column("rule_composite_score", sa.Float(), nullable=True),
        sa.Column("consensus_score", sa.Float(), nullable=True),
        sa.Column("final_rank", sa.Integer(), nullable=True),
        sa.Column("executive_summary", sa.Text(), nullable=True),
        sa.Column("is_disqualified", sa.Boolean(), server_default=sa.false()),
        sa.Column("disqualify_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
    )
    op.create_index("ix_job_results_job_id", "job_results", ["job_id"])
    op.create_index("ix_job_results_candidate_id", "job_results", ["candidate_id"])

    # ── agent_reviews ──────────────────────────────────────────────────────
    agent_type_enum = postgresql.ENUM(
        "tech_specialist", "trajectory_specialist", "behavioral_specialist",
        name="agent_type",
    )

    op.create_table(
        "agent_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_type", agent_type_enum, nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("pros", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
        sa.Column("cons", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_result_id"], ["job_results.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_agent_reviews_job_result_id", "agent_reviews", ["job_result_id"])


def downgrade() -> None:
    op.drop_table("agent_reviews")
    op.execute("DROP TYPE IF EXISTS agent_type")
    op.drop_table("job_results")
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS job_stage")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.drop_table("candidates")
    op.drop_table("users")
