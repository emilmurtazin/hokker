from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import ExerciseAgeGroup, ExerciseCategory, ExerciseLevel


class Exercise(Base):
    """
    Видеоупражнение из библиотеки. Само видео не хранится на нашем сервере —
    video_url ссылается на внешний хостинг (YouTube/Vimeo/S3 и т.п.).
    Полноценная загрузка файлов — отдельная инфраструктурная задача
    (нужно файловое хранилище), не входит в этот шаг.
    """

    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[ExerciseCategory] = mapped_column(
        Enum(ExerciseCategory, name="exercise_category"), nullable=False, index=True
    )
    age_group: Mapped[ExerciseAgeGroup] = mapped_column(
        Enum(ExerciseAgeGroup, name="exercise_age_group"), nullable=False, index=True
    )
    level: Mapped[ExerciseLevel] = mapped_column(
        Enum(ExerciseLevel, name="exercise_level"), nullable=False, index=True
    )
    video_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # что развивает
    repetitions: Mapped[str | None] = mapped_column(String(255), nullable=True)  # напр. "3x10"
    key_points: Mapped[str | None] = mapped_column(Text, nullable=True)  # ключевые точки техники
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
