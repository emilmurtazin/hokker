from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.coach_players import router as coach_players_router
from app.api.coaches import router as coaches_router
from app.api.children import router as children_router
from app.api.sessions import router as sessions_router
from app.api.bookings import router as bookings_router
from app.api.attendance import router as attendance_router
from app.api.ratings import router as ratings_router
from app.api.arenas import router as arenas_router
from app.api.exercises import router as exercises_router
from app.api.telegram import router as telegram_router

app = FastAPI(
    title="ХОККЕР API",
    description="Платформа для тренеров, родителей и арен",
    version="0.1.0",
)

app.include_router(auth_router)
app.include_router(users_router)
# ВАЖНО: coach_players_router регистрируется РАНЬШЕ coaches_router — у него
# литеральные пути /coaches/lookup-parent и /coaches/me/players, а в
# coaches_router есть параметризованный /coaches/{coach_id}, который иначе
# перехватил бы эти запросы первым (см. аналогичный фикс в sessions.py).
app.include_router(coach_players_router)
app.include_router(coaches_router)
app.include_router(children_router)
app.include_router(sessions_router)
app.include_router(bookings_router)
app.include_router(attendance_router)
app.include_router(ratings_router)
app.include_router(arenas_router)
app.include_router(exercises_router)
app.include_router(telegram_router)


@app.get("/health")
def health_check():
    """Простая проверка, что сервис жив."""
    return {"status": "ok"}


@app.get("/health/db")
def health_check_db(db: Session = Depends(get_db)):
    """Проверка, что подключение к PostgreSQL работает."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
