"""
Единая сборка ответа с данными пользователя (UserOut).

Раньше deep-link для привязки Telegram собирался только в GET /users/me, а ответы
входа и регистрации отдавали пользователя без ссылки. Из-за этого сразу после
входа кнопка «Привязать Telegram» в профиле показывала «Скоро» и оживала только
после обновления страницы (когда фронтенд заново запрашивал /users/me).
Теперь все три места (/users/me, вход, регистрация) идут через build_user_out().
"""

import secrets

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.telegram_link_token import TelegramLinkToken
from app.models.user import User
from app.schemas.auth import UserOut


def build_user_out(user: User, db: Session) -> UserOut:
    out = UserOut.model_validate(user)

    bot = (settings.TELEGRAM_BOT_USERNAME or "").lstrip("@")
    out.telegram_bot_username = bot or None

    # Ссылка привязки нужна только пока Telegram не привязан и бот настроен.
    # Для уже привязанных не плодим лишние токены в БД при каждом запросе профиля.
    if not bot or user.telegram_chat_id:
        out.telegram_deep_link = None
        return out

    # Один актуальный неиспользованный токен на пользователя.
    db.execute(
        delete(TelegramLinkToken).where(
            TelegramLinkToken.user_id == user.id,
            TelegramLinkToken.used.is_(False),
        )
    )
    link = TelegramLinkToken(user_id=user.id, token=secrets.token_urlsafe(32))
    db.add(link)
    db.commit()
    db.refresh(link)

    out.telegram_deep_link = f"https://t.me/{bot}?start={link.token}"
    return out
