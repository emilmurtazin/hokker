"""manual session participants

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("bookings", "player_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column("bookings", sa.Column("manual_player_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    # Ручных участников нельзя безопасно представить как зарегистрированных
    # игроков в старой схеме, поэтому перед откатом они удаляются.
    op.execute("DELETE FROM bookings WHERE player_id IS NULL")
    op.drop_column("bookings", "manual_player_name")
    op.alter_column("bookings", "player_id", existing_type=sa.BigInteger(), nullable=False)
