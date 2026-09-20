"""
Единое форматирование для текстов уведомлений и ответов бота.

Раньше заголовок тренировки собирался в трёх местах (bookings.py, sessions.py,
ratings.py) как f"{session.type.value} {datetime}" — в Telegram уходило
«ice 21.09 в 15:00»: сырое имя enum и время в UTC, а не в часовом поясе
пользователя. Теперь всё идёт через session_title().
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

# Те же названия, что и на фронтенде (src/utils/labels.js → SESSION_TYPE_LABELS).
SESSION_TYPE_LABELS = {
    "ice": "Лёд",
    "off_ice": "ОФП",
    "shooting": "Броски",
    "theory": "Теория",
    "game": "Игра",
    "goalie": "Вратарская",
}

_WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def app_tz() -> ZoneInfo:
    """Часовой пояс приложения (APP_TIMEZONE). При опечатке — Москва, а не падение."""
    try:
        return ZoneInfo(settings.APP_TIMEZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Moscow")


def to_local(dt: datetime) -> datetime:
    """Переводит datetime в часовой пояс приложения. Naive-значение считаем UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(app_tz())


def format_dt(dt: datetime) -> str:
    """'21.09 (пн) в 18:00' — в часовом поясе приложения."""
    local = to_local(dt)
    return f"{local.strftime('%d.%m')} ({_WEEKDAYS[local.weekday()]}) в {local.strftime('%H:%M')}"


def type_label(session_type) -> str:
    value = getattr(session_type, "value", session_type)
    return SESSION_TYPE_LABELS.get(value, str(value))


def session_title(session) -> str:
    """'Лёд 21.09 (пн) в 18:00' — то, что попадает в текст уведомления."""
    return f"{type_label(session.type)} {format_dt(session.datetime_)}"


def session_info(session) -> str:
    """'Лёд 21.09 (пн) в 18:00, 60 мин, Арена «Северная»' — для сообщения об изменении."""
    parts = [session_title(session)]
    if getattr(session, "duration_minutes", None):
        parts.append(f"{session.duration_minutes} мин")
    if getattr(session, "arena_name", None):
        parts.append(session.arena_name)
    return ", ".join(parts)


def is_quiet_hours(now: datetime | None = None) -> bool:
    """True, если сейчас «тихие часы» (по APP_TIMEZONE) и напоминания слать не нужно."""
    hour = to_local(now or datetime.now(timezone.utc)).hour
    start, end = settings.QUIET_HOURS_START, settings.QUIET_HOURS_END
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end  # окно переходит через полночь (22 → 8)
