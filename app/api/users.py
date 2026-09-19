from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_telegram_link_token
from app.models.user import User
from app.schemas.auth import UserOut, UserUpdateIn

router = APIRouter(prefix="/users", tags=["users"])


def _build_user_out(user: User) -> UserOut:
    """
    Собирает ответ профиля. Ссылку на бота генерируем сразу при запросе —
    так она попадает в HTML с первого рендера, и переход работает нативной
    навигацией браузера (как в spasibo-kollege).
    """
    out = UserOut.model_validate(user)

    if settings.TELEGRAM_BOT_USERNAME:
        token = create_telegram_link_token(user.id)
        out.telegram_deep_link = (
            f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={token}"
        )
    else:
        out.telegram_deep_link = None

    return out


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return _build_user_out(user)


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
    return _build_user_out(user)
