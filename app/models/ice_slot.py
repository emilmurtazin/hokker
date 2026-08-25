from datetime import date, datetime, time

from sqlalchemy import BigInteger, Date, DateTime, Enum, ForeignKey, Numeric, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import IceType, SlotStatus


class IceSlot(Base):
    """
    Свободный (или уже забронированный) промежуток льда, который
    администратор арены выставляет в каталог для тренеров.
    """

    __tablename__ = "ice_slots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    arena_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("arenas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    time_start: Mapped[time] = mapped_column(Time, nullable=False)
    time_end: Mapped[time] = mapped_column(Time, nullable=False)
    ice_type: Mapped[IceType] = mapped_column(Enum(IceType, name="ice_type"), nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)  # справочно
    status: Mapped[SlotStatus] = mapped_column(
        Enum(SlotStatus, name="slot_status"), nullable=False, default=SlotStatus.available
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    arena: Mapped["Arena"] = relationship()
