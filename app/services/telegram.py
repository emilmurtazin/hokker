"""
Обёртка над Telegram Bot API. Никакого отдельного long-polling процесса —
бот работает через webhook: Telegram сам стучится на наш публичный HTTPS-адрес
(см. app/api/telegram.py, /internal/telegram/webhook), отдельный воркер не нужен.
"""

import httpx

from app.core.config import settings


class TelegramError(Exception):
    pass


def send_message(chat_id: str, text: str) -> None:
    """
    Отправляет сообщение пользователю. Если TELEGRAM_BOT_TOKEN не задан
    (например, локальная разработка без настоящего бота) — просто печатает
    в консоль вместо реальной отправки, аналогично ConsoleSMSProvider.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        print(f"[DEV TELEGRAM] -> chat_id={chat_id}: {text}")
        return

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        response = httpx.post(
            url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10.0
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        # Уведомление — не критичная для бизнес-логики операция: если Telegram
        # недоступен, основной запрос (например, подтверждение записи) не должен
        # падать целиком. Логируем и идём дальше.
        # TODO: когда появится Celery — переотправлять такие сбои через retry,
        # а не просто терять уведомление.
        print(f"[TELEGRAM ERROR] Не удалось отправить сообщение chat_id={chat_id}: {e}")


def set_webhook(webhook_url: str) -> dict:
    """Утилита для одноразовой настройки — вызывается вручную, не из приложения."""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook"
    response = httpx.post(url, json={"url": webhook_url}, timeout=10.0)
    response.raise_for_status()
    return response.json()
