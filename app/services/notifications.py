"""
Единая точка отправки уведомлений. Бизнес-код (bookings.py, sessions.py и т.д.)
не знает про Telegram напрямую — вызывает notify(event, user, **context),
а этот модуль решает, кому и что отправить.

Что умеет:
  - к каждому уведомлению прикладывается кнопка «Открыть …», которая ведёт
    сразу на нужный экран приложения (внутри Telegram);
  - отправка идёт в фоновом пуле потоков: медленный Telegram или прокси
    (таймаут до 10 с) больше не задерживает ответ основного запроса —
    например, «Подтвердить запись» у тренера;
  - сбой в уведомлении никогда не ломает основной запрос: запись/отмена уже
    сохранены в БД, а исключение из notify() превратило бы их в HTTP 500.

Переезд на Celery по-прежнему возможен: достаточно заменить _pool.submit(...)
на send_notification.delay(...).
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.models.user import User
from app.services.telegram import esc, open_app_markup, send_message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    text: str  # шаблон; подстановки {name} — значения экранируются автоматически
    button: str  # подпись кнопки под сообщением
    path: str  # экран приложения по умолчанию (можно переопределить: notify(..., path=...))


# Пути соответствуют маршрутам фронтенда (src/App.jsx) для роли получателя.
EVENTS: dict[str, Event] = {
    # --- тренеру ---
    "new_booking_request": Event(
        "🆕 Новая заявка на «{session_title}»\nУченик: {player_name}\n"
        "Подтвердите или отклоните в приложении.",
        "Открыть заявки",
        "/",
    ),
    "new_booking": Event(
        "✅ Новая запись на «{session_title}»\nУченик: {player_name}",
        "Открыть тренировку",
        "/",
    ),
    "booking_cancelled": Event(
        "❌ Запись отменена: «{session_title}»\nУченик: {player_name}",
        "Открыть тренировку",
        "/",
    ),
    "ice_request_approved": Event(
        "✅ Ваша заявка на лёд подтверждена: {slot_info}.", "Открыть «Лёд»", "/ice"
    ),
    "ice_request_rejected": Event(
        "❌ Ваша заявка на лёд отклонена: {slot_info}.", "Открыть «Лёд»", "/ice"
    ),
    # --- родителю ---
    "booking_approved": Event(
        "🎉 Тренер подтвердил запись на «{session_title}».", "Открыть расписание", "/schedule"
    ),
    "booking_rejected": Event(
        "😔 Тренер отклонил запись на «{session_title}».", "Открыть расписание", "/schedule"
    ),
    "waitlist_slot_available": Event(
        "🎟 Освободилось место на «{session_title}»!\n"
        "Подтвердите в приложении в течение 15 минут, иначе место уйдёт следующему.",
        "Подтвердить место",
        "/schedule",
    ),
    "waitlist_expired": Event(
        "⌛ Время на подтверждение места на «{session_title}» истекло. "
        "Место перешло следующему в очереди.",
        "Открыть расписание",
        "/schedule",
    ),
    "session_cancelled": Event(
        "🚫 Тренировка «{session_title}» отменена тренером.", "Открыть расписание", "/schedule"
    ),
    "session_updated": Event(
        "🔄 Тренер изменил тренировку.\nБыло: {old_info}\nСтало: {new_info}",
        "Открыть расписание",
        "/schedule",
    ),
    "session_reminder": Event(
        "⏰ Скоро тренировка!\n{player_name}: {session_title}{place}",
        "Открыть расписание",
        "/schedule",
    ),
    "coach_invite": Event(
        "🤝 Тренер {coach_name} добавил вас в базу учеников. Подтвердите в приложении.",
        "Открыть профиль",
        "/profile",
    ),
    "rating_added": Event(
        "⭐ Тренер выставил новые оценки за «{session_title}». Посмотрите прогресс в приложении.",
        "Смотреть прогресс",
        "/schedule",
    ),
    # --- администратору арены ---
    "ice_request_new": Event(
        "🧊 Новая заявка от тренера {coach_name} на слот: {slot_info}.",
        "Открыть заявки",
        "/requests",
    ),
    "ice_request_cancelled": Event(
        "🚫 Тренер {coach_name} отменил заявку на слот: {slot_info}.",
        "Открыть заявки",
        "/requests",
    ),
}

# Небольшой пул: уведомления уходят параллельно и не блокируют HTTP-запрос.
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tg-notify")


class _SafeContext(dict):
    """Пропущенная подстановка даёт пустую строку, а не KeyError."""

    def __missing__(self, key):
        return ""


def _deliver(chat_id: str, text: str, markup: dict | None) -> None:
    try:
        send_message(chat_id, text, markup)
    except Exception:  # send_message сам не бросает, но поток не должен умирать молча
        logger.exception("Не удалось отправить уведомление chat_id=%s", chat_id)


def notify(event: str, user: User | None, *, path: str | None = None, **context) -> None:
    """
    Отправляет уведомление пользователю, если у него привязан Telegram.
    Если telegram_chat_id не задан — молча ничего не делает (привязка опциональна).

    path — необязательный экран приложения для кнопки (например, '/sessions/12');
    по умолчанию берётся из EVENTS.
    """
    try:
        if user is None or not user.telegram_chat_id:
            return

        spec = EVENTS.get(event)
        if spec is None:
            logger.error("Неизвестное событие уведомления: %s", event)
            return

        # Значения приходят из БД/пользовательского ввода (названия, имена) —
        # экранируем, т.к. send_message шлёт с parse_mode=HTML.
        safe_context = _SafeContext({key: esc(value) for key, value in context.items()})
        text = spec.text.format_map(safe_context)
        markup = open_app_markup(spec.button, path or spec.path)
        _pool.submit(_deliver, user.telegram_chat_id, text, markup)
    except Exception:
        logger.exception("Ошибка подготовки уведомления %s", event)


def flush() -> None:
    """Дожидается отправки всех поставленных в очередь уведомлений (тесты, остановка сервиса)."""
    global _pool
    old, _pool = _pool, ThreadPoolExecutor(max_workers=4, thread_name_prefix="tg-notify")
    old.shutdown(wait=True)
