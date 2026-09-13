from fastapi import APIRouter, Depends, Header, HTTPException, Request

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
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """
    Сюда Telegram сам присылает апдейты (после настройки через setWebhook).
    Не вызывается напрямую из приложения — это эндпоинт для внешнего сервиса.
    """
    if settings.TELEGRAM_WEBHOOK_SECRET:
        if x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Неверный секрет вебхука")

    update = await request.json()
    message = update.get("message")
    if not message:
        # Не текстовое сообщение (например, edited_message, callback_query) — игнорируем.
        return {"ok": True}

    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id")

    if not text.startswith("/start") or chat_id is None:
        return {"ok": True}

    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        send_message(str(chat_id), "Эта ссылка должна открываться из приложения 24hokker.ru.")
        return {"ok": True}

    token = parts[1]
    try:
        payload = decode_token(token)
    except JWTError:
        send_message(str(chat_id), "Ссылка устарела. Сгенерируйте новую в приложении.")
        return {"ok": True}

    if payload.get("type") != "telegram_link":
        send_message(str(chat_id), "Некорректная ссылка привязки.")
        return {"ok": True}

    user = db.get(User, int(payload["sub"]))
    if user is None:
        send_message(str(chat_id), "Пользователь не найден.")
        return {"ok": True}

    user.telegram_chat_id = str(chat_id)
    db.commit()

    send_message(str(chat_id), "✅ Telegram успешно привязан к вашему аккаунту 24hokker.ru!")
    return {"ok": True}
