"""coach join_code: постоянный код для самостоятельного присоединения родителей

Добавляет coaches.join_code (уникальный 6-значный код) и join_code_changed_at.
Для уже существующих тренеров бэкфиллит уникальные коды прямо в миграции —
NOT NULL/UNIQUE накладывается только после того, как у каждой строки есть
значение.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-22 10:00:00.000000

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MIN, _MAX = 100_000, 999_999


def _random_code() -> str:
    return str(secrets.randbelow(_MAX - _MIN + 1) + _MIN)


def upgrade() -> None:
    op.add_column('coaches', sa.Column('join_code', sa.String(length=6), nullable=True))
    op.add_column(
        'coaches', sa.Column('join_code_changed_at', sa.DateTime(timezone=True), nullable=True)
    )

    conn = op.get_bind()
    coaches = sa.table('coaches', sa.column('id', sa.BigInteger), sa.column('join_code', sa.String))
    ids = [row[0] for row in conn.execute(sa.select(coaches.c.id))]

    used: set[str] = set()
    for coach_id in ids:
        for _ in range(30):
            code = _random_code()
            if code not in used:
                used.add(code)
                break
        else:  # практически невозможно при 900 000 вариантов, но не молчим
            raise RuntimeError("Не удалось подобрать уникальный код тренера при миграции")
        conn.execute(coaches.update().where(coaches.c.id == coach_id).values(join_code=code))

    op.alter_column('coaches', 'join_code', nullable=False)
    # Один уникальный индекс — как и остальные unique+index колонки в проекте
    # (auth_codes.request_id, users.phone и т. д.), а не индекс + отдельный
    # constraint: так соответствует тому, что опишет модель (mapped_column(...,
    # unique=True, index=True)), и alembic check не увидит расхождения.
    op.create_index(op.f('ix_coaches_join_code'), 'coaches', ['join_code'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_coaches_join_code'), table_name='coaches')
    op.drop_column('coaches', 'join_code_changed_at')
    op.drop_column('coaches', 'join_code')
