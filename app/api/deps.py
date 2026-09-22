from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token, JWTError
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=True)
# Для публичных эндпоинтов, у которых есть «персональная» часть (лента тренировок):
# без токена — обычный посетитель, с токеном — конкретный пользователь.
optional_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или просроченный токен",
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ожидался access-токен",
        )

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )
    return user


def require_role(*allowed_roles: str):
    """
    Пример использования в эндпоинте:
        @router.post("/sessions")
        def create_session(user: User = Depends(require_role("coach"))): ...
    """

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Доступно только для ролей: {', '.join(allowed_roles)}",
            )
        return user

    return dependency


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """
    Пользователь, если пришёл токен, иначе None. Просроченный/неверный токен — 401,
    а не молчаливое «аноним»: фронтенд по 401 обновляет токен и повторяет запрос,
    иначе родитель случайно потерял бы в ленте свои закрытые тренировки.
    """
    if credentials is None:
        return None
    return get_current_user(credentials, db)
