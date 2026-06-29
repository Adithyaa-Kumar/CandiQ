"""merge_heads

Revision ID: 189025be9f28
Revises: a1b2c3d4e5f6, 303057991824
Create Date: 2026-06-29 07:34:07.765396

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '189025be9f28'
down_revision: Union[str, None] = ('a1b2c3d4e5f6', '303057991824')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
