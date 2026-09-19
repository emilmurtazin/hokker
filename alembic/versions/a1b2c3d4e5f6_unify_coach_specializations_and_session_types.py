"""unify coach specializations and session types

Revision ID: a1b2c3d4e5f6
Revises: 6406093f105b
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "6406093f105b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Тип занятий получает вратарскую тренировку без изменения существующих данных.
    op.execute("ALTER TYPE session_type ADD VALUE IF NOT EXISTS 'goalie'")

    # В PostgreSQL нельзя удалить значения из ENUM. Пересоздаём тип и одновременно
    # переводим устаревшие специализации в ближайшие актуальные типы тренировок.
    op.execute("ALTER TYPE specialization RENAME TO specialization_old")
    op.execute(
        "CREATE TYPE specialization AS ENUM "
        "('ice', 'off_ice', 'shooting', 'theory', 'game', 'goalie')"
    )
    op.execute(
        "ALTER TABLE coaches ALTER COLUMN specializations TYPE specialization[] "
        "USING array_replace("
        "array_replace(specializations::text[], 'skating', 'ice'), "
        "'general', 'off_ice')::specialization[]"
    )
    op.execute("DROP TYPE specialization_old")


def downgrade() -> None:
    # При откате новые типы занятий и специализации переводятся в ближайшие
    # значения старой схемы, чтобы миграция оставалась выполнимой при наличии данных.
    op.execute("ALTER TYPE session_type RENAME TO session_type_new")
    op.execute("CREATE TYPE session_type AS ENUM ('ice', 'off_ice', 'shooting', 'theory', 'game')")
    op.execute(
        "ALTER TABLE training_sessions ALTER COLUMN type TYPE session_type "
        "USING CASE WHEN type::text = 'goalie' THEN 'ice' ELSE type::text END::session_type"
    )
    op.execute("DROP TYPE session_type_new")

    op.execute("ALTER TYPE specialization RENAME TO specialization_new")
    op.execute(
        "CREATE TYPE specialization AS ENUM "
        "('skating', 'shooting', 'off_ice', 'goalie', 'general')"
    )
    op.execute(
        "ALTER TABLE coaches ALTER COLUMN specializations TYPE specialization[] "
        "USING array_replace("
        "array_replace(array_replace(specializations::text[], 'ice', 'skating'), 'theory', 'general'), "
        "'game', 'general')::specialization[]"
    )
    op.execute("DROP TYPE specialization_new")
