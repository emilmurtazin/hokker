from datetime import datetime

from sqlalchemy import BigInteger, String, Integer, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import SessionType, SessionVisibility


class TrainingSession(Base):
    """Тренировка, созданная тренером."""

    __tablename__ = "training_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coach_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[SessionType] = mapped_column(Enum(SessionType, name="session_type"), nullable=False)
    visibility: Mapped[SessionVisibility] = mapped_column(
        Enum(SessionVisibility, name="session_visibility"), nullable=False
    )
    datetime_: Mapped[datetime] = mapped_column(
        "datetime", DateTime(timezone=True), nullable=False, index=True
    )

    # Задел под Этап 4 (аренда льда) — согласовано заранее, чтобы не мигрировать
    # данные позже. На Этапе 1 тренер вводит arena_name текстом,
    # arena_id остаётся пустым.
    arena_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("arenas.id", ondelete="SET NULL"), nullable=True
    )
    arena_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    max_players: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    coach: Mapped["User"] = relationship()
    arena: Mapped["Arena"] = relationship()
    bookings: Mapped[list["Booking"]] = relationship(back_populates="session")
