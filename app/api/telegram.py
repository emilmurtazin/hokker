import hmac

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_telegram_link_token, decode_token, JWTError
from app.models.user import User
from app.schemas.telegram import TelegramLinkOut
from app.services.telegram import send_message

router = APIRouter(tags=["telegram"])


@router.get("/telegram/link", response_model=TelegramLinkOut)
def get_link(user: User = Depends(get_current_user)):
    if not settings.TELEGRAM_BOT_USERNAME:
        raise HTTPException(
            status_code=503,
            detail="Telegram-бот ещё не настроен на сервере (TELEGRAM_BOT_USERNAME пуст)",
        )
    token = create_telegram_link_token(user.id)
    deep_link = f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={token}"
    return TelegramLinkOut(deep_link=deep_link)


@router.post("/internal/telegram/webhook")
async def telegram_webhook(
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """
    Сюда Telegram сам присылает апдейты (после настройки через setWebhook).
    Не вызывается напрямую из приложения — это эндпоинт для внешнего сервиса.

    Ответы пользователю отправляются в фоне (BackgroundTasks): Telegram ждёт
    ответ на вебхук считанные секунды и при таймауте повторяет апдейт, а
    отправка идёт через прокси и синхронным httpx — в async-обработчике она
    заблокировала бы весь event loop.
    """
    if settings.TELEGRAM_WEBHOOK_SECRET:
        received = (x_telegram_bot_api_secret_token or "").encode()
        expected = settings.TELEGRAM_WEBHOOK_SECRET.encode()
        if not hmac.compare_digest(received, expected):
            raise HTTPException(status_code=401, detail="Неверный секрет вебхука")

    update = await request.json()
    message = update.get("message")
    if not message:
        # Не текстовое сообщение (например, edited_message, callback_query) — игнорируем.
        return {"ok": True}

    text = message.get("text") or ""
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if not text.startswith("/start") or chat_id is None:
        return {"ok": True}

    # Привязываем только личные чаты: если бота добавили в группу, в chat_id
    # окажется id группы, и уведомления пользователя уходили бы всем участникам.
    if chat.get("type") != "private":
        return {"ok": True}

    def reply(reply_text: str, reply_markup: dict | None = None) -> dict:
        background.add_task(send_message, str(chat_id), reply_text, reply_markup)
        return {"ok": True}

    def reply_welcome() -> dict:
        """Приветствие для тех, кто открыл бота напрямую (без deep-link)."""
        app_url = settings.APP_PUBLIC_URL or "https://24hokker.ru"
        text_out = (
            "👋 Привет! Я бот Хоккер.\n\n"
            "Чтобы привязать Telegram к вашему аккаунту:\n"
            "1. Войдите в приложение 24hokker.ru\n"
            "2. Перейдите в Профиль → «Привязать Telegram»\n"
            "3. Нажмите кнопку — откроется бот прямо в Telegram"
        )
        markup = {
            "inline_keyboard": [
                [{"text": "🔗 Перейти на сайт", "url": app_url}],
            ]
        }
        return reply(text_out, markup)

    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        # Пользователь открыл бота напрямую, без ?start=<token> из приложения.
        return reply_welcome()

    token = parts[1]
    try:
        payload = decode_token(token)
    except JWTError:
        return reply("Ссылка устарела. Сгенерируйте новую в приложении.")

    if payload.get("type") != "telegram_link":
        return reply("Некорректная ссылка привязки.")

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return reply("Некорректная ссылка привязки.")

    user = db.get(User, user_id)
    if user is None:
        return reply("Пользователь не найден.")

    # telegram_chat_id уникален. Без этой проверки повторная привязка чата к
    # другому аккаунту падала бы с IntegrityError → 500, а Telegram повторял бы
    # такой апдейт снова и снова.
    already_taken = (
        db.query(User)
        .filter(User.telegram_chat_id == str(chat_id), User.id != user.id)
        .first()
    )
    if already_taken is not None:
        return reply(
            "Этот Telegram уже привязан к другому аккаунту 24hokker.ru. "
            "Если это ошибка — напишите в поддержку."
        )

    if user.telegram_chat_id != str(chat_id):
        user.telegram_chat_id = str(chat_id)
        db.commit()

    return reply("✅ Telegram успешно привязан к вашему аккаунту 24hokker.ru!")
