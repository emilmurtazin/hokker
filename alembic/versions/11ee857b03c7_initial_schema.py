"""initial schema

Revision ID: 11ee857b03c7
Revises:
Create Date: 2026-08-24 03:22:02.731826

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '11ee857b03c7'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "role",
            sa.Enum("coach", "parent", "arena_admin", name="user_role"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("telegram_chat_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    op.create_index("ix_users_telegram_chat_id", "users", ["telegram_chat_id"], unique=True)

    # --- arenas (задел под Этап 4) --------------------------------------
    op.create_table(
        "arenas",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
    )

    # --- coaches ---------------------------------------------------------
    op.create_table(
        "coaches",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "specialization",
            sa.Enum(
                "skating", "shooting", "off_ice", "goalie", "general",
                name="specialization",
            ),
            nullable=False,
        ),
        sa.Column("experience_years", sa.Integer(), nullable=True),
        sa.Column("about", sa.Text(), nullable=True),
        sa.Column("age_groups", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- players -----------------------------------------------------------
    op.create_table(
        "players",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column(
            "position",
            sa.Enum("forward", "defense", "goalie", name="player_position"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_players_parent_id", "players", ["parent_id"])

    # --- coach_players -------------------------------------------------------
    op.create_table(
        "coach_players",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "coach_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "player_id",
            sa.BigInteger(),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "pending", "removed", name="coach_player_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("coach_id", "player_id", name="uq_coach_player"),
    )
    op.create_index("ix_coach_players_coach_id", "coach_players", ["coach_id"])
    op.create_index("ix_coach_players_player_id", "coach_players", ["player_id"])

    # --- training_sessions -----------------------------------------------------
    op.create_table(
        "training_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "coach_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "type",
            sa.Enum("ice", "off_ice", "shooting", "theory", "game", name="session_type"),
            nullable=False,
        ),
        sa.Column(
            "visibility",
            sa.Enum("open", "closed", name="session_visibility"),
            nullable=False,
        ),
        sa.Column("datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "arena_id",
            sa.BigInteger(),
            sa.ForeignKey("arenas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("arena_name", sa.String(length=255), nullable=True),
        sa.Column("max_players", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_training_sessions_coach_id", "training_sessions", ["coach_id"])
    op.create_index("ix_training_sessions_datetime", "training_sessions", ["datetime"])

    # --- bookings ------------------------------------------------------------
    op.create_table(
        "bookings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("training_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "player_id",
            sa.BigInteger(),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "confirmed", "waiting", "invited",
                "cancelled", "rejected", "expired",
                name="booking_status",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "player_id", name="uq_session_player"),
    )
    op.create_index("ix_bookings_session_id", "bookings", ["session_id"])
    op.create_index("ix_bookings_player_id", "bookings", ["player_id"])


def downgrade() -> None:
    op.drop_table("bookings")
    op.drop_table("training_sessions")
    op.drop_table("coach_players")
    op.drop_table("players")
    op.drop_table("coaches")
    op.drop_table("arenas")
    op.drop_table("users")

    # PostgreSQL требует явно удалить enum-типы отдельно от таблиц
    sa.Enum(name="booking_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="session_visibility").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="session_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="coach_player_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="player_position").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="specialization").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
