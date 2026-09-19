from fastapi import APIRouter, Depends
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.telegram_link_token import TelegramLinkToken
from app.schemas.auth import UserOut, UserUpdateIn

router = APIRouter(prefix="/users", tags=["users"])


def _build_user_out(user: User, db: Session) -> UserOut:
    """
    Собирает ответ профиля. Короткий токен привязки Telegram генерируется
    и сохраняется в БД прямо здесь — он уходит в deep-link.
    """
    out = UserOut.model_validate(user)

    if settings.TELEGRAM_BOT_USERNAME:
        # Удаляем все прежние неиспользованные токены пользователя
        db.execute(
            delete(TelegramLinkToken).where(
                TelegramLinkToken.user_id == user.id,
                TelegramLinkToken.used.is_(False),
            )
        )
        # Создаём новый
        import secrets
        link = TelegramLinkToken(user_id=user.id, token=secrets.token_urlsafe(32))
        db.add(link)
        db.commit()
        db.refresh(link)

        out.telegram_deep_link = (
            f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={link.token}"
        )
    else:
        out.telegram_deep_link = None

    return out


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _build_user_out(user, db)


@router.patch("/me", response_model=UserOut)
def update_me(
    data: UserUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return _build_user_out(user, db)