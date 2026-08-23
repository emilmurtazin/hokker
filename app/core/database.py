from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""
    pass


def get_db():
    """
    Dependency для FastAPI: открывает сессию БД на время запроса
    и гарантированно закрывает её после.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
