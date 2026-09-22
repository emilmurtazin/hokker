import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.coach_players import router as coach_players_router
from app.api.client_groups import router as client_groups_router
from app.api.coaches import router as coaches_router
from app.api.children import router as children_router
from app.api.sessions import router as sessions_router
from app.api.bookings import router as bookings_router
from app.api.attendance import router as attendance_router
from app.api.ratings import router as ratings_router
from app.api.arenas import router as arenas_router
from app.api.exercises import router as exercises_router
from app.api.telegram import router as telegram_router
from app.services.scheduler import scheduler_loop
from app.services.telegram import setup_bot_profile

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    При старте: (1) обновляем профиль бота — команды меню, описание, кнопку «Меню»
    (идемпотентно, в фоне: недоступный Telegram/прокси не задерживает запуск);
    (2) запускаем фоновый планировщик — напоминания и истечение приглашений.
    """
    # Если браузер пишет «Не получилось…» при запросах к API — первым делом смотрят сюда:
    # адрес сайта в адресной строке должен быть в этом списке (CORS).
    logger.warning("[CORS] разрешённые адреса фронтенда: %s", ", ".join(settings.cors_origins_list))

    tasks: list[asyncio.Task] = []
    if settings.TELEGRAM_BOT_TOKEN:
        tasks.append(asyncio.create_task(asyncio.to_thread(setup_bot_profile)))
    if settings.SCHEDULER_ENABLED:
        tasks.append(asyncio.create_task(scheduler_loop()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()


app = FastAPI(
    title="24hokker.ru API",
    description="Платформа для тренеров, родителей и арен",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
# ВАЖНО: coach_players_router регистрируется РАНЬШЕ coaches_router — у него
# литеральные пути /coaches/lookup-parent и /coaches/me/players, а в
# coaches_router есть параметризованный /coaches/{coach_id}, который иначе
# перехватил бы эти запросы первым (см. аналогичный фикс в sessions.py).
app.include_router(coach_players_router)
app.include_router(client_groups_router)
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
