"""client groups: группы клиентов тренера и доступ к закрытым тренировкам

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'client_groups',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('coach_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['coach_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('coach_id', 'name', name='uq_client_group_name'),
    )
    op.create_index(op.f('ix_client_groups_coach_id'), 'client_groups', ['coach_id'])

    op.create_table(
        'client_group_members',
        sa.Column('group_id', sa.BigInteger(), nullable=False),
        sa.Column('coach_player_id', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['client_groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['coach_player_id'], ['coach_players.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('group_id', 'coach_player_id'),
    )
    op.create_index(
        op.f('ix_client_group_members_coach_player_id'), 'client_group_members', ['coach_player_id']
    )

    op.create_table(
        'session_groups',
        sa.Column('session_id', sa.BigInteger(), nullable=False),
        sa.Column('group_id', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['training_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['client_groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('session_id', 'group_id'),
    )
    op.create_index(op.f('ix_session_groups_group_id'), 'session_groups', ['group_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_session_groups_group_id'), table_name='session_groups')
    op.drop_table('session_groups')
    op.drop_index(op.f('ix_client_group_members_coach_player_id'), table_name='client_group_members')
    op.drop_table('client_group_members')
    op.drop_index(op.f('ix_client_groups_coach_id'), table_name='client_groups')
    op.drop_table('client_groups')
