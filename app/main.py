from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.auth import router as auth_router
from app.api.users import router as users_router

app = FastAPI(
    title="ХОККЕР API",
    description="Платформа для тренеров, родителей и арен",
    version="0.1.0",
)

app.include_router(auth_router)
app.include_router(users_router)


@app.get("/health")
def health_check():
    """Простая проверка, что сервис жив."""
    return {"status": "ok"}


@app.get("/health/db")
def health_check_db(db: Session = Depends(get_db)):
    """Проверка, что подключение к PostgreSQL работает."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
