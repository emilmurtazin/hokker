"""
Единая точка отправки уведомлений. Бизнес-код (bookings.py, sessions.py и т.д.)
не знает про Telegram напрямую — вызывает notify(event, user, **context),
а этот модуль решает, кому и что отправить.

TODO: когда появится Celery, notify() должен не отправлять синхронно,
а ставить задачу в очередь (send_notification.delay(...)) — тогда сбой
Telegram не будет удлинять время ответа основного запроса.
"""

from app.models.user import User
from app.services.telegram import send_message

# Тексты соответствуют таблице событий из раздела 9 ТЗ.
_TEMPLATES = {
    "new_booking_request": "🆕 Новая заявка от родителя на «{session_title}». Подтвердите в приложении.",
    "new_booking": "✅ Новая запись на «{session_title}».",
    "booking_cancelled": "❌ Отменена запись на «{session_title}».",
    "booking_approved": "🎉 Тренер подтвердил запись на «{session_title}».",
    "booking_rejected": "😔 Тренер отклонил запись на «{session_title}».",
    "waitlist_slot_available": (
        "🎟 Освободилось место на «{session_title}»! "
        "Подтвердите в приложении в течение 15 минут, иначе место уйдёт следующему."
    ),
    "waitlist_expired": "⌛ Время на подтверждение места на «{session_title}» истекло.",
    "session_cancelled": "🚫 Тренировка «{session_title}» отменена тренером.",
}


def notify(event: str, user: User, **context) -> None:
    """
    Отправляет уведомление пользователю, если у него привязан Telegram.
    Если telegram_chat_id не задан — молча ничего не делает (пользователь
    просто не получит уведомление; это не ошибка, привязка Telegram опциональна).
    """
    if not user.telegram_chat_id:
        return

    template = _TEMPLATES.get(event)
    if template is None:
        raise ValueError(f"Неизвестное событие уведомления: {event}")

    text = template.format(**context)
    send_message(user.telegram_chat_id, text)
