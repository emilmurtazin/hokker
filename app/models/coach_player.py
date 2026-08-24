from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import CoachPlayerStatus


class CoachPlayer(Base):
    """
    Агрегированная связь «ребёнок числится в базе тренера».
    Создаётся автоматически при первом подтверждённом booking,
    либо вручную тренером (тогда status=pending до подтверждения родителем).
    См. согласованную логику из обсуждения ТЗ.
    """

    __tablename__ = "coach_players"
    __table_args__ = (
        UniqueConstraint("coach_id", "player_id", name="uq_coach_player"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coach_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[CoachPlayerStatus] = mapped_column(
        Enum(CoachPlayerStatus, name="coach_player_status"),
        nullable=False,
        default=CoachPlayerStatus.pending,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    coach: Mapped["User"] = relationship(foreign_keys=[coach_id])
    player: Mapped["Player"] = relationship(foreign_keys=[player_id])
