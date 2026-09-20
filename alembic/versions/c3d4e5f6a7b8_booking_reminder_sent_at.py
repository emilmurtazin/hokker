"""booking reminder_sent_at

Отметка «напоминание о тренировке уже отправлено» — чтобы фоновая задача
не присылала одно и то же напоминание повторно.

Revision ID: c3d4e5f6a7b8
Revises: 969445fceb21
Create Date: 2026-09-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = '969445fceb21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'bookings',
        sa.Column('reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('bookings', 'reminder_sent_at')
