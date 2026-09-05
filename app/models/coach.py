from datetime import datetime

from sqlalchemy import BigInteger, Integer, Text, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ExerciseAgeGroup, Specialization


class Coach(Base):
    """
    Профиль тренера. Расширяет User дополнительными полями.
    id совпадает с users.id (связь один-к-одному).
    """

    __tablename__ = "coaches"

    id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Массив — тренер может вести несколько направлений одновременно.
    specializations: Mapped[list[Specialization]] = mapped_column(
        ARRAY(Enum(Specialization, name="specialization")), nullable=False
    )
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Массив фиксированных возрастных категорий (те же, что и в видеоупражнениях) —
    # тренер может выбрать несколько.
    age_groups: Mapped[list[ExerciseAgeGroup] | None] = mapped_column(
        ARRAY(Enum(ExerciseAgeGroup, name="exercise_age_group")), nullable=True
    )
    visible_in_search: Mapped[bool] = mapped_column(
        default=True, server_default="true", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="coach_profile")
