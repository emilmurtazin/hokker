"""user blocking (admin moderation)

Revision ID: 2b4d6f8a1c3e
Revises: c9d0e1f2a3b4
Create Date: 2026-09-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2b4d6f8a1c3e'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('is_blocked', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'users',
        sa.Column('blocked_reason', sa.String(length=500), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('blocked_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'blocked_at')
    op.drop_column('users', 'blocked_reason')
    op.drop_column('users', 'is_blocked')
