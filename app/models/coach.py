from datetime import datetime

from sqlalchemy import BigInteger, String, Integer, Text, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import Specialization


class Coach(Base):
    """
    Профиль тренера. Расширяет User дополнительными полями.
    id совпадает с users.id (связь один-к-одному).
    """

    __tablename__ = "coaches"

    id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    specialization: Mapped[Specialization] = mapped_column(
        Enum(Specialization, name="specialization"), nullable=False
    )
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Возрастные группы храним как текст с перечислением через запятую,
    # например "6-9,10-12,13+" — для Этапа 1 этого достаточно,
    # при необходимости позже можно вынести в отдельную таблицу.
    age_groups: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="coach_profile")
