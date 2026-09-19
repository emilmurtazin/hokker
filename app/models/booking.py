from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import BookingStatus


class Booking(Base):
    """
    Запись ребёнка на тренировку. Полный жизненный цикл, включая
    лист ожидания (waiting -> invited -> confirmed/expired).
    """

    __tablename__ = "bookings"
    __table_args__ = (
        # ребёнок не может быть дважды записан на одну и ту же тренировку
        UniqueConstraint("session_id", "player_id", name="uq_session_player"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Для ученика, которого ещё нет в приложении, тренер указывает только имя.
    manual_player_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status"), nullable=False, default=BookingStatus.pending
    )
    # момент, когда родителю ушло приглашение с листа ожидания —
    # используется Celery-задачей для таймера 15 минут
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["TrainingSession"] = relationship(back_populates="bookings")
    player: Mapped["Player"] = relationship()
