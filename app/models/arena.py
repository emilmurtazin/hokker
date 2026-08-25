from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Arena(Base):
    """
    Профиль арены. id совпадает с users.id (администратор арены) —
    связь один-к-одному, аналогично профилю тренера (Coach).
    """

    __tablename__ = "arenas"

    id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ice_size: Mapped[str | None] = mapped_column(String(100), nullable=True)  # напр. "60x30 м"
    locker_rooms: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    admin: Mapped["User"] = relationship()
