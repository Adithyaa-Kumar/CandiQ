"""add confidence and normalized_score to job_results

Revision ID: a1b2c3d4e5f6
Revises: d4c1611d96eb
Create Date: 2026-06-22

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'd4c1611d96eb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('job_results', sa.Column('normalized_score', sa.Float(), nullable=True))
    op.add_column('job_results', sa.Column('confidence', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('job_results', 'confidence')
    op.drop_column('job_results', 'normalized_score')
