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
from typing import NoReturn

import httpx
from fastapi import HTTPException

from app.core.config import DEFAULT_PUBLIC_URL, settings

# Лимит Telegram на длину одного сообщения (после разбора HTML-разметки).
MAX_TEXT_LEN = 4096
# Лимит на подпись к фото — в четыре раза меньше, чем у обычного сообщения.
MAX_CAPTION_LEN = 1024


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


def _fit(text: str, max_len: int = MAX_TEXT_LEN) -> str:
    """
    Укладывает текст в лимит Telegram. Режем по пробелу/переводу строки, а не
    посреди слова: так не разрезается HTML-сущность вида &amp;.
    """
    if len(text) <= max_len:
        return text
    limit = max_len - 2
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


def send_photo_strict(
    chat_id: str,
    photo_url: str,
    caption: str,
    reply_markup: dict | None = None,
    parse_mode: str | None = "HTML",
) -> None:
    """
    Отправляет картинку по публичному HTTPS-адресу (Telegram сам скачивает её)
    с подписью (до 1024 символов) и необязательной клавиатурой. Бросает TelegramError.
    Без TELEGRAM_BOT_TOKEN (локальная разработка) печатает в консоль.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        print(f"[DEV TELEGRAM PHOTO] -> chat_id={chat_id}: {photo_url}\n{caption}")
        return

    payload: dict = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": _fit(caption, MAX_CAPTION_LEN),
    }
    if parse_mode is not None:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    _call("sendPhoto", payload)


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
        raise_http_error(e, chat_id)


def raise_http_error(e: TelegramError, chat_id: str) -> NoReturn:
    """Превращает сбой Telegram в понятную HTTP-ошибку (её покажет фронтенд)."""
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


# ---------------------------------------------------------------------------
# Кнопки, которые открывают приложение (24hokker.ru) прямо внутри Telegram
# ---------------------------------------------------------------------------


def app_base_url() -> str:
    return (settings.APP_PUBLIC_URL or DEFAULT_PUBLIC_URL).rstrip("/")


def app_url(path: str = "/") -> str:
    """Полный адрес раздела приложения: app_url('/schedule') → https://24hokker.ru/schedule."""
    if not path.startswith("/"):
        path = "/" + path
    return app_base_url() + path


def _webapp_supported() -> bool:
    # Telegram принимает Web App только по HTTPS; на локальной разработке
    # (http://localhost) вместо этого используем обычную ссылку.
    return app_base_url().startswith("https://")


def open_app_button(text: str, path: str = "/") -> dict:
    """Inline-кнопка: открывает раздел приложения внутри Telegram (Mini App)."""
    if _webapp_supported():
        return {"text": text, "web_app": {"url": app_url(path)}}
    return {"text": text, "url": app_url(path)}


def open_app_markup(text: str, path: str = "/") -> dict:
    return {"inline_keyboard": [[open_app_button(text, path)]]}


def reply_keyboard(rows: list[list[tuple[str, str]]]) -> dict | None:
    """
    Постоянная клавиатура под полем ввода. rows — [[(подпись, путь), ...], ...].
    Каждая кнопка открывает нужный раздел приложения одним нажатием (KeyboardButton.web_app).
    Reply-кнопки умеют только Web App, поэтому без HTTPS клавиатуру не показываем.
    """
    if not _webapp_supported():
        return None
    return {
        "keyboard": [
            [{"text": label, "web_app": {"url": app_url(path)}} for label, path in row]
            for row in rows
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "input_field_placeholder": "Выберите раздел или нажмите «Меню»",
    }


REMOVE_KEYBOARD = {"remove_keyboard": True}


# ---------------------------------------------------------------------------
# Профиль бота: меню команд, описание, кнопка «Меню»
# ---------------------------------------------------------------------------

# Одно меню на все роли: что именно покажет команда, бот решает по роли
# пользователя (см. app/services/telegram_bot.py).
BOT_COMMANDS = [
    {"command": "menu", "description": "Главное меню"},
    {"command": "schedule", "description": "Расписание и тренировки"},
    {"command": "requests", "description": "Заявки и приглашения"},
    {"command": "exercises", "description": "Каталог упражнений"},
    {"command": "profile", "description": "Профиль и настройки"},
    {"command": "help", "description": "Помощь"},
]

BOT_DESCRIPTION = (
    "Хоккер — платформа для тренеров, родителей и арен.\n"
    "Здесь приходят уведомления о записях, тренировках и заявках, "
    "а кнопки меню открывают нужные разделы приложения."
)
BOT_SHORT_DESCRIPTION = "Уведомления и быстрый доступ к 24hokker.ru"


def setup_bot_profile() -> None:
    """
    Идемпотентная настройка бота: команды, описание, кнопка «Меню».
    Вызывается при старте приложения (в фоновом потоке). Каждый шаг независим:
    сбой одного (например, недоступен прокси) не мешает остальным и не роняет сервис.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        return

    if settings.TELEGRAM_MENU_BUTTON == "webapp" and _webapp_supported():
        menu_button = {"type": "web_app", "text": "Хоккер", "web_app": {"url": app_url("/")}}
    else:
        menu_button = {"type": "commands"}

    steps = [
        ("setMyCommands", {"commands": BOT_COMMANDS}),
        ("setMyDescription", {"description": BOT_DESCRIPTION}),
        ("setMyShortDescription", {"short_description": BOT_SHORT_DESCRIPTION}),
        ("setChatMenuButton", {"menu_button": menu_button}),
    ]
    for method, payload in steps:
        try:
            _call(method, payload)
        except TelegramError as e:
            print(f"[TELEGRAM SETUP] {e}")
    print("[TELEGRAM SETUP] профиль бота обновлён (команды, описание, меню)")


def set_webhook(webhook_url: str, secret_token: str | None = None) -> dict:
    """
    Утилита для одноразовой настройки — вызывается вручную, не из приложения.
    secret_token должен совпадать с TELEGRAM_WEBHOOK_SECRET.
    """
    payload: dict = {"url": webhook_url, "allowed_updates": ["message"]}
    if secret_token:
        payload["secret_token"] = secret_token
    return _call("setWebhook", payload)
