from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import SlotRequestStatus


class SlotRequest(Base):
    """Заявка тренера на бронирование конкретного слота льда."""

    __tablename__ = "slot_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ice_slots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    coach_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[SlotRequestStatus] = mapped_column(
        Enum(SlotRequestStatus, name="slot_request_status"),
        nullable=False,
        default=SlotRequestStatus.pending,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    slot: Mapped["IceSlot"] = relationship()
    coach: Mapped["User"] = relationship()
