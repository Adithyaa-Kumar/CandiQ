"""candidate pools

Revision ID: f2792ec743a3
Revises: be3ede912c66
Create Date: 2026-06-18 09:48:15.485136

BUG FIX: original migration added `pool_id UUID NOT NULL` to the
candidates table with no server_default and no backfill, which caused
`alembic upgrade head` to fail with:
  "column 'pool_id' of relation 'candidates' contains null values"
on any database that already had candidate rows.

Fix: add the column nullable=True first, then create a sentinel pool
to backfill existing rows, THEN apply the NOT NULL constraint. On a
fresh database this is a no-op; on an existing one it keeps data intact.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f2792ec743a3'
down_revision: Union[str, None] = 'be3ede912c66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── candidate_pools table ────────────────────────────────────────────
    op.create_table(
        'candidate_pools',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_candidate_pools_owner_id'), 'candidate_pools', ['owner_id'], unique=False)

    # ── Add pool_id to candidates — nullable first to allow backfill ─────
    op.add_column('candidates', sa.Column('pool_id', sa.Uuid(), nullable=True))

    # Backfill: for each distinct owner_id that already has candidates,
    # create one sentinel pool and assign all their existing candidates to it.
    bind = op.get_bind()
    owner_rows = bind.execute(
        sa.text("SELECT DISTINCT owner_id FROM candidates WHERE pool_id IS NULL")
    ).fetchall()

    import uuid
    from datetime import datetime, timezone

    for (owner_id,) in owner_rows:
        pool_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO candidate_pools (id, owner_id, name, created_at) "
                "VALUES (:id, :owner_id, :name, :now)"
            ),
            {
                "id": pool_id,
                "owner_id": str(owner_id),
                "name": "Migrated pool",
                "now": datetime.now(timezone.utc),
            },
        )
        bind.execute(
            sa.text(
                "UPDATE candidates SET pool_id = :pool_id "
                "WHERE owner_id = :owner_id AND pool_id IS NULL"
            ),
            {"pool_id": pool_id, "owner_id": str(owner_id)},
        )

    # Now it's safe to enforce NOT NULL
    op.alter_column('candidates', 'pool_id', nullable=False)

    op.drop_index('ix_candidates_owner_external', table_name='candidates')
    op.create_index(op.f('ix_candidates_pool_id'), 'candidates', ['pool_id'], unique=False)
    op.create_unique_constraint('uq_pool_candidate', 'candidates', ['pool_id', 'external_id'])
    op.create_foreign_key(None, 'candidates', 'candidate_pools', ['pool_id'], ['id'])

    # ── Add candidate_pool_id to jobs — nullable first ───────────────────
    op.add_column('jobs', sa.Column('candidate_pool_id', sa.Uuid(), nullable=True))

    # Backfill jobs: assign each job to its owner's most recent pool
    job_rows = bind.execute(
        sa.text("SELECT id, owner_id FROM jobs WHERE candidate_pool_id IS NULL")
    ).fetchall()
    for (job_id, owner_id) in job_rows:
        pool_row = bind.execute(
            sa.text(
                "SELECT id FROM candidate_pools WHERE owner_id = :owner_id "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"owner_id": str(owner_id)},
        ).fetchone()
        if pool_row:
            bind.execute(
                sa.text("UPDATE jobs SET candidate_pool_id = :pid WHERE id = :jid"),
                {"pid": str(pool_row[0]), "jid": str(job_id)},
            )

    op.alter_column('jobs', 'candidate_pool_id', nullable=False)
    op.create_index(op.f('ix_jobs_candidate_pool_id'), 'jobs', ['candidate_pool_id'], unique=False)
    op.create_foreign_key(None, 'jobs', 'candidate_pools', ['candidate_pool_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(None, 'jobs', type_='foreignkey')
    op.drop_index(op.f('ix_jobs_candidate_pool_id'), table_name='jobs')
    op.drop_column('jobs', 'candidate_pool_id')
    op.drop_constraint(None, 'candidates', type_='foreignkey')
    op.drop_constraint('uq_pool_candidate', 'candidates', type_='unique')
    op.drop_index(op.f('ix_candidates_pool_id'), table_name='candidates')
    op.create_index('ix_candidates_owner_external', 'candidates', ['owner_id', 'external_id'], unique=False)
    op.drop_column('candidates', 'pool_id')
    op.drop_index(op.f('ix_candidate_pools_owner_id'), table_name='candidate_pools')
    op.drop_table('candidate_pools')