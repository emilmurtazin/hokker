"""
Единая точка отправки уведомлений. Бизнес-код (bookings.py, sessions.py и т.д.)
не знает про Telegram напрямую — вызывает notify(event, user, **context),
а этот модуль решает, кому и что отправить.

TODO: когда появится Celery, notify() должен не отправлять синхронно,
а ставить задачу в очередь (send_notification.delay(...)) — тогда сбой
Telegram не будет удлинять время ответа основного запроса.
"""

from app.models.user import User
from app.services.telegram import esc, send_message

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
    "coach_invite": "🤝 Тренер {coach_name} добавил вас в базу учеников. Подтвердите в приложении.",
    "rating_added": "⭐ Тренер выставил новые оценки за «{session_title}». Посмотрите прогресс в приложении.",
    "ice_request_new": "🧊 Новая заявка от тренера {coach_name} на слот: {slot_info}.",
    "ice_request_approved": "✅ Ваша заявка на лёд подтверждена: {slot_info}.",
    "ice_request_rejected": "❌ Ваша заявка на лёд отклонена: {slot_info}.",
    "ice_request_cancelled": "🚫 Тренер {coach_name} отменил заявку на слот: {slot_info}.",
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

    # Значения приходят из БД/пользовательского ввода (названия, имена) —
    # экранируем, т.к. send_message шлёт с parse_mode=HTML.
    safe_context = {key: esc(value) for key, value in context.items()}
    text = template.format(**safe_context)
    send_message(user.telegram_chat_id, text)
