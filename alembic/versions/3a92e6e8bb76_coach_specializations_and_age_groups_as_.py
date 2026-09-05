"""coach specializations and age groups as arrays

Revision ID: 3a92e6e8bb76
Revises: 61e9ad33ff71
Create Date: 2026-08-31 18:10:23.386331

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '3a92e6e8bb76'
down_revision: Union[str, None] = '61e9ad33ff71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Безопасный перенос данных: сначала добавляем новые колонки как
    # nullable, переносим существующие значения, только потом убираем
    # старые колонки — чтобы не потерять данные тренеров, которые уже
    # заполнили профиль на проде.

    # --- specialization (одно значение) -> specializations (массив) ---
    op.add_column(
        'coaches',
        sa.Column(
            'specializations',
            postgresql.ARRAY(sa.Enum('skating', 'shooting', 'off_ice', 'goalie', 'general', name='specialization')),
            nullable=True,
        ),
    )
    op.execute("UPDATE coaches SET specializations = ARRAY[specialization]::specialization[]")
    op.alter_column('coaches', 'specializations', nullable=False)
    op.drop_column('coaches', 'specialization')

    # --- age_groups (текст "6-9,10-12") -> age_groups (массив enum) ---
    op.add_column(
        'coaches',
        sa.Column(
            'age_groups_new',
            postgresql.ARRAY(sa.Enum('age_6_9', 'age_10_12', 'age_13_plus', name='exercise_age_group')),
            nullable=True,
        ),
    )
    # Разбираем старую строку по запятым и сопоставляем известным значениям.
    # Всё, что не распозналось (опечатки, старый свободный текст) — просто
    # пропускается, а не роняет миграцию.
    op.execute("""
        UPDATE coaches SET age_groups_new = (
            SELECT array_agg(mapped)
            FROM (
                SELECT CASE trim(part)
                    WHEN '6-9' THEN 'age_6_9'
                    WHEN '10-12' THEN 'age_10_12'
                    WHEN '13+' THEN 'age_13_plus'
                    ELSE NULL
                END::exercise_age_group AS mapped
                FROM unnest(string_to_array(coaches.age_groups, ',')) AS part
            ) sub
            WHERE mapped IS NOT NULL
        )
        WHERE coaches.age_groups IS NOT NULL
    """)
    op.drop_column('coaches', 'age_groups')
    op.alter_column('coaches', 'age_groups_new', new_column_name='age_groups')


def downgrade() -> None:
    # Обратная миграция теряет информацию о "лишних" специализациях/группах
    # (оставляет только первую) — это ожидаемо для downgrade такого рода.
    op.alter_column('coaches', 'age_groups', new_column_name='age_groups_old')
    op.add_column('coaches', sa.Column('age_groups', sa.VARCHAR(length=255), nullable=True))
    op.execute("""
        UPDATE coaches SET age_groups = (
            SELECT string_agg(
                CASE val::text
                    WHEN 'age_6_9' THEN '6-9'
                    WHEN 'age_10_12' THEN '10-12'
                    WHEN 'age_13_plus' THEN '13+'
                END, ','
            )
            FROM unnest(age_groups_old) AS val
        )
        WHERE age_groups_old IS NOT NULL
    """)
    op.drop_column('coaches', 'age_groups_old')

    op.add_column(
        'coaches',
        sa.Column('specialization', postgresql.ENUM('skating', 'shooting', 'off_ice', 'goalie', 'general', name='specialization'), nullable=True),
    )
    op.execute("UPDATE coaches SET specialization = specializations[1]")
    op.alter_column('coaches', 'specialization', nullable=False)
    op.drop_column('coaches', 'specializations')
