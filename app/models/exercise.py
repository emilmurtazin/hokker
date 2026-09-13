from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import (
    ExerciseAgeGroup,
    ExerciseCategory,
    ExerciseContentStatus,
    ExerciseLocation,
)


class Exercise(Base):
    """
    Упражнение из библиотеки — по структуре повторяет иллюстрированные
    карточки школы (ОФП-01, ОФП-02 и т.д.). Видео пока нет — есть
    иллюстрированная карточка с шагами выполнения; video_url и image_url
    оставлены на будущее (nullable), когда появится реальный контент.
    """

    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # короткий подзаголовок

    category: Mapped[ExerciseCategory] = mapped_column(
        Enum(ExerciseCategory, name="exercise_category"), nullable=False, index=True
    )
    location: Mapped[ExerciseLocation] = mapped_column(
        Enum(ExerciseLocation, name="exercise_location"), nullable=False, index=True
    )
    age_group: Mapped[ExerciseAgeGroup] = mapped_column(
        Enum(ExerciseAgeGroup, name="exercise_age_group"), nullable=False, index=True
    )

    players_text: Mapped[str | None] = mapped_column(String(50), nullable=True)   # "4–10", "2"
    duration_text: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "5 минут"
    equipment_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    needs_puck: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    steps: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)          # "Как выполнять"
    coach_tips: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)     # "Подсказки тренера"
    simplify_tips: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)  # "Упростить"
    complicate_tips: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)  # "Усложнить"
    hockey_connection: Mapped[str | None] = mapped_column(Text, nullable=True)  # "Связь с хоккеем"
    qualities: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)), nullable=True)  # теги качеств

    content_status: Mapped[ExerciseContentStatus] = mapped_column(
        Enum(ExerciseContentStatus, name="exercise_content_status"),
        nullable=False,
        default=ExerciseContentStatus.draft,
    )

    video_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
