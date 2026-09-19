"""
Обёртка над Telegram Bot API. Никакого отдельного long-polling процесса —
бот работает через webhook: Telegram сам стучится на наш публичный HTTPS-адрес
(см. app/api/telegram.py, /internal/telegram/webhook), отдельный воркер не нужен.

TELEGRAM_PROXY_URL: api.telegram.org недоступен напрямую с российских серверов
(включая Timeweb) — Telegram заблокирован Роскомнадзором. Если задать
TELEGRAM_PROXY_URL, все запросы к Bot API пойдут через него — например,
через зарубежный сервер (см. README, раздел про настройку прокси).

Две функции отправки:
  - send_message()        — «мягкая»: для фоновых уведомлений. Не бросает
                            исключений, возвращает True/False.
  - send_message_strict() — «жёсткая»: для действий, где человек ждёт результата
                            («написать родителю», «отправить упражнение»).
                            Бросает TelegramError, чтобы API мог честно
                            ответить ошибкой, а не «Отправлено».

ВАЖНО: тексты уходят с parse_mode=HTML. Всё, что попало из пользовательского
ввода или из БД (имена, названия, комментарии), нужно оборачивать в esc(),
иначе символы < > & ломают разметку, и Telegram отклоняет сообщение целиком.
"""

import html

import httpx
from fastapi import HTTPException

from app.core.config import settings

# Лимит Telegram на длину одного сообщения (после разбора HTML-разметки).
MAX_TEXT_LEN = 4096


class TelegramError(Exception):
    """
    Ошибка отправки. Текст сообщения НАМЕРЕННО не содержит URL запроса: в нём
    зашит токен бота (…/bot<TOKEN>/sendMessage), а исключения httpx его
    включают — иначе токен утёк бы в логи.
    """

    def __init__(self, message: str, *, blocked: bool = False):
        super().__init__(message)
        # True, если пользователь заблокировал бота / удалил аккаунт (HTTP 403).
        self.blocked = blocked


def esc(value) -> str:
    """Экранирует пользовательский текст для parse_mode=HTML."""
    return html.escape(str(value), quote=False)


def _fit(text: str) -> str:
    """
    Укладывает текст в лимит Telegram. Режем по пробелу/переводу строки, а не
    посреди слова: так не разрезается HTML-сущность вида &amp;.
    """
    if len(text) <= MAX_TEXT_LEN:
        return text
    limit = MAX_TEXT_LEN - 2
    cut = max(text.rfind("\n", 0, limit), text.rfind(" ", 0, limit))
    if cut < limit // 2:
        cut = limit
    return text[:cut].rstrip() + " …"


def _client() -> httpx.Client:
    """
    httpx-клиент с прокси, если он настроен. Поддерживает и обычный HTTP(S)-
    прокси (http://user:pass@host:port), и SOCKS5 (socks5://host:port) —
    для SOCKS5 дополнительно нужен пакет httpx[socks] (уже в requirements.txt).
    """
    if settings.TELEGRAM_PROXY_URL:
        return httpx.Client(proxy=settings.TELEGRAM_PROXY_URL, timeout=10.0)
    return httpx.Client(timeout=10.0)


def _call(method: str, payload: dict) -> dict:
    """Вызов метода Bot API. Бросает TelegramError (без токена в тексте)."""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"
    try:
        with _client() as client:
            response = client.post(url, json=payload)
    except httpx.HTTPError as e:
        # Только тип ошибки (ConnectTimeout, ProxyError…) — str(e) может
        # содержать URL с токеном.
        raise TelegramError(f"{method}: сеть/прокси недоступны ({type(e).__name__})") from None

    if response.status_code != 200:
        try:
            description = response.json().get("description", "")
        except ValueError:
            description = ""
        raise TelegramError(
            f"{method}: HTTP {response.status_code} {description}".strip(),
            blocked=response.status_code == 403,
        )
    return response.json()


def send_message_strict(
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
    parse_mode: str | None = "HTML",
) -> None:
    """
    Отправляет сообщение и бросает TelegramError, если не получилось.
    Без TELEGRAM_BOT_TOKEN (локальная разработка) печатает в консоль.

    reply_markup — необязательная inline-клавиатура, например
        {"inline_keyboard": [[{"text": "Открыть", "url": "https://..."}]]}
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        print(f"[DEV TELEGRAM] -> chat_id={chat_id}: {text}")
        return

    payload: dict = {"chat_id": chat_id, "text": _fit(text)}
    if parse_mode is not None:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    _call("sendMessage", payload)


def send_message(
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
    parse_mode: str | None = "HTML",
) -> bool:
    """
    «Мягкая» отправка для уведомлений: сбой Telegram не должен ронять основной
    запрос (например, подтверждение записи). Ошибку логируем и возвращаем False.
    TODO: когда появится Celery — переотправлять такие сбои через retry.
    """
    try:
        send_message_strict(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
        return True
    except TelegramError as e:
        print(f"[TELEGRAM ERROR] chat_id={chat_id}: {e}")
        return False


def send_message_or_http_error(
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
    parse_mode: str | None = "HTML",
) -> None:
    """
    Для эндпоинтов, где человек нажимает «Отправить»: при сбое отдаём понятную
    HTTP-ошибку, которую фронтенд покажет вместо ложного «Отправлено в Telegram».
    """
    try:
        send_message_strict(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramError as e:
        print(f"[TELEGRAM ERROR] chat_id={chat_id}: {e}")
        if e.blocked:
            raise HTTPException(
                status_code=409,
                detail="Родитель остановил бота в Telegram — пусть заново нажмёт «Привязать Telegram» в профиле",
            ) from None
        raise HTTPException(
            status_code=502,
            detail="Не удалось отправить сообщение в Telegram. Попробуйте чуть позже.",
        ) from None


def set_webhook(webhook_url: str, secret_token: str | None = None) -> dict:
    """
    Утилита для одноразовой настройки — вызывается вручную, не из приложения.
    secret_token должен совпадать с TELEGRAM_WEBHOOK_SECRET.
    """
    payload: dict = {"url": webhook_url, "allowed_updates": ["message"]}
    if secret_token:
        payload["secret_token"] = secret_token
    return _call("setWebhook", payload)
