from datetime import datetime

from sqlalchemy import BigInteger, String, DateTime, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import UserRole


class User(Base):
    """
    Общая таблица для всех ролей (тренер / родитель / админ арены).
    Специфичные для роли поля живут в отдельных таблицах (см. Coach).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # связи
    coach_profile: Mapped["Coach"] = relationship(back_populates="user", uselist=False)
    children: Mapped[list["Player"]] = relationship(back_populates="parent")
