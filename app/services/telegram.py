"""
Сервис для работы с Telegram Bot API.

Бот работает через webhook: Telegram сам стучится на наш публичный HTTPS-адрес
(см. app/api/telegram.py, /internal/telegram/webhook), отдельный воркер не нужен.

Все вызовы Bot API идут синхронным httpx — предполагается, что из async-кода
они вызываются через BackgroundTasks (см. app/api/telegram.py).
"""

import httpx

from app.core.config import settings


def _api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"


def send_message(
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
    parse_mode: str | None = None,
) -> dict:
    """
    Отправляет текстовое сообщение в чат.

    :param chat_id: id чата (строка или число), куда слать
    :param text: текст сообщения
    :param reply_markup: необязательная inline-клавиатура, например
        {"inline_keyboard": [[{"text": "Открыть", "url": "https://..."}]]}
    :param parse_mode: "HTML" или "MarkdownV2", если нужно форматирование
    :return: ответ Telegram API (dict)
    """
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if parse_mode is not None:
        payload["parse_mode"] = parse_mode

    with httpx.Client(timeout=20.0) as client:
        response = client.post(_api_url("sendMessage"), json=payload)
        response.raise_for_status()
        return response.json()


def set_webhook(webhook_url: str, secret_token: str | None = None) -> dict:
    """
    Регистрирует вебхук в Telegram. Секрет должен совпадать с
    TELEGRAM_WEBHOOK_SECRET, иначе бэкенд будет отклонять апдейты (401).
    """
    payload: dict = {"url": webhook_url, "allowed_updates": ["message"]}
    if secret_token:
        payload["secret_token"] = secret_token

    with httpx.Client(timeout=20.0) as client:
        response = client.post(_api_url("setWebhook"), json=payload)
        response.raise_for_status()
        return response.json()


def get_webhook_info() -> dict:
    """Возвращает текущее состояние вебхука (url, last_error_message и т.д.)."""
    with httpx.Client(timeout=20.0) as client:
        response = client.get(_api_url("getWebhookInfo"))
        response.raise_for_status()
        return response.json()
