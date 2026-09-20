"""
Фоновые задачи без Celery и без отдельного воркера: обычный asyncio-цикл внутри
процесса API (запускается в lifespan, см. app/main.py). Раз в минуту:

  1. expire_waitlist_invites — приглашение из листа ожидания живёт 15 минут.
     Если родитель не подтвердил, запись переходит в expired, родитель получает
     уведомление, а место предлагается следующему в очереди. Раньше это
     происходило только когда сам родитель нажимал «Подтвердить» после срока.

  2. send_session_reminders — напоминание родителю за REMINDER_HOURS_BEFORE часов
     до тренировки (не ночью, см. QUIET_HOURS_*).

Защита от дублей при нескольких запущенных копиях приложения: каждая задача
сначала «захватывает» строку атомарным UPDATE ... WHERE (статус/отметка ещё не
менялись) и шлёт уведомление только если захват удался (rowcount == 1).
Побочный эффект: при сбое Telegram повтора не будет (at-most-once) — это
лучше, чем спамить повторами.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.booking import Booking
from app.models.enums import BookingStatus
from app.models.player import Player
from app.models.training_session import TrainingSession
from app.models.user import User
from app.services.formatting import is_quiet_hours, session_title
from app.services.notifications import notify

logger = logging.getLogger(__name__)


def expire_waitlist_invites(db: Session) -> int:
    """Возвращает, сколько приглашений истекло."""
    # Импорт здесь, а не наверху: bookings.py — модуль API, не тянем его при импорте сервиса.
    from app.api.bookings import WAITLIST_INVITE_TTL_MINUTES, _promote_next_waiting

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=WAITLIST_INVITE_TTL_MINUTES)

    candidates = (
        db.query(Booking.id, Booking.session_id, Booking.player_id, TrainingSession.datetime_)
        .join(TrainingSession, TrainingSession.id == Booking.session_id)
        .filter(Booking.status == BookingStatus.invited, Booking.invited_at < cutoff)
        .all()
    )

    expired = 0
    for booking_id, session_id, player_id, session_dt in candidates:
        claimed = db.execute(
            update(Booking)
            .where(Booking.id == booking_id, Booking.status == BookingStatus.invited)
            .values(status=BookingStatus.expired)
        ).rowcount
        db.commit()
        if claimed != 1:
            continue  # параллельно успел родитель (confirm) или другая копия приложения
        expired += 1

        if session_dt <= now:
            continue  # тренировка уже началась — очередь двигать и сообщать незачем

        session = db.get(TrainingSession, session_id)
        player = db.get(Player, player_id) if player_id else None
        if player is not None:
            notify(
                "waitlist_expired",
                db.get(User, player.parent_id),
                session_title=session_title(session),
            )
        _promote_next_waiting(db, session_id)
    return expired


def send_session_reminders(db: Session) -> int:
    """Возвращает, сколько напоминаний отправлено."""
    hours = settings.REMINDER_HOURS_BEFORE
    if hours <= 0 or is_quiet_hours():
        return 0

    now = datetime.now(timezone.utc)
    window = timedelta(hours=hours)

    rows = (
        db.query(Booking.id, Booking.player_id, TrainingSession)
        .join(TrainingSession, TrainingSession.id == Booking.session_id)
        .filter(
            Booking.status == BookingStatus.confirmed,
            Booking.player_id.is_not(None),
            Booking.reminder_sent_at.is_(None),
            TrainingSession.datetime_ > now,
            TrainingSession.datetime_ <= now + window,
            # Записались уже внутри окна напоминания (например, за час до начала) —
            # «напоминать» о только что сделанной записи бессмысленно.
            Booking.created_at <= TrainingSession.datetime_ - window,
        )
        .all()
    )

    sent = 0
    for booking_id, player_id, session in rows:
        claimed = db.execute(
            update(Booking)
            .where(
                Booking.id == booking_id,
                Booking.reminder_sent_at.is_(None),
                Booking.status == BookingStatus.confirmed,
            )
            .values(reminder_sent_at=func.now())
        ).rowcount
        db.commit()
        if claimed != 1:
            continue

        player = db.get(Player, player_id)
        if player is None:
            continue
        notify(
            "session_reminder",
            db.get(User, player.parent_id),
            player_name=player.name,
            session_title=session_title(session),
            place=f"\n📍 {session.arena_name}" if session.arena_name else "",
        )
        sent += 1
    return sent


def run_once() -> None:
    """Один проход всех задач. Каждая изолирована: сбой одной не мешает другой."""
    for job in (expire_waitlist_invites, send_session_reminders):
        db = SessionLocal()
        try:
            job(db)
        except Exception:
            logger.exception("Фоновая задача %s завершилась ошибкой", job.__name__)
            db.rollback()
        finally:
            db.close()


async def scheduler_loop() -> None:
    interval = max(15, settings.SCHEDULER_INTERVAL_SECONDS)
    await asyncio.sleep(5)  # дать приложению полностью подняться
    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception:
            logger.exception("Сбой цикла планировщика")
        await asyncio.sleep(interval)
