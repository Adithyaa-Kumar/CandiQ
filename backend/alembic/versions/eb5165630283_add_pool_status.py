"""add_pool_status

Revision ID: eb5165630283
Revises: d4c1611d96eb
Create Date: 2026-06-19 10:20:28.923420

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eb5165630283'
down_revision: Union[str, None] = 'd4c1611d96eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():

    pool_status = sa.Enum(
        "processing",
        "ready",
        "failed",
        name="pool_status",
    )

    pool_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "candidate_pools",
        sa.Column(
            "status",
            pool_status,
            nullable=False,
            server_default="processing",
        ),
    )

def downgrade():

    op.drop_column("candidate_pools", "status")

    pool_status = sa.Enum(
        "processing",
        "ready",
        "failed",
        name="pool_status",
    )

    pool_status.drop(op.get_bind(), checkfirst=True)