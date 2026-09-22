"""
Группы клиентов тренера («Утренняя группа», «Вратари» …).

Три таблицы:
  client_groups         — сама группа (принадлежит тренеру);
  client_group_members  — кто в группе: связь «ученик в базе тренера» (coach_players);
  session_groups        — каким группам доступна закрытая тренировка.

Ученик может состоять в нескольких группах. Классы связей намеренно без
relationship(): удаление строк каскадом делает БД (ON DELETE CASCADE), а не ORM
(с ORM-каскадом отмена тренировки уже однажды падала с 500 — см. TrainingSession).
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ClientGroup(Base):
    __tablename__ = "client_groups"
    __table_args__ = (UniqueConstraint("coach_id", "name", name="uq_client_group_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coach_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClientGroupMember(Base):
    __tablename__ = "client_group_members"

    group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("client_groups.id", ondelete="CASCADE"), primary_key=True
    )
    coach_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("coach_players.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )


class SessionGroup(Base):
    __tablename__ = "session_groups"

    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("training_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("client_groups.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
