from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import SkillCategory


class Rating(Base):
    """
    Оценка ребёнка по одной из категорий навыков за конкретную тренировку.
    Один и тот же навык за одну тренировку у одного ребёнка — только одна
    запись (уникальность), повторная простановка перезаписывает значение
    (аналогично Attendance — тренер может скорректировать позже).
    """

    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("session_id", "player_id", "skill", name="uq_rating_session_player_skill"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill: Mapped[SkillCategory] = mapped_column(Enum(SkillCategory, name="skill_category"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..5, проверяется на уровне API
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    session: Mapped["TrainingSession"] = relationship()
    player: Mapped["Player"] = relationship()
