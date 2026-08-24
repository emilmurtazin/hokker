from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Arena(Base):
    """
    Минимальная модель арены — пока используется только как цель для
    training_sessions.arena_id. Полная реализация (адрес, характеристики,
    админ арены и т.д.) появится на Этапе 4.
    """

    __tablename__ = "arenas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
