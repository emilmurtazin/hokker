import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError

from app.core.config import settings


def hash_code(code: str) -> str:
    """
    Хэширует OTP-код перед сохранением в БД (не храним в открытом виде).
    HMAC-SHA256 с секретом приложения в роли pepper — этого достаточно
    для короткоживущего 4-значного кода с лимитом попыток, полноценный
    bcrypt здесь избыточен (используется для настоящих паролей, не OTP).
    """
    return hmac.new(
        settings.JWT_SECRET_KEY.encode(), code.encode(), hashlib.sha256
    ).hexdigest()


def verify_code(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_code(code), code_hash)


def create_access_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> tuple[str, str, datetime]:
    """
    Возвращает (token, jti, expires_at).
    jti и expires_at нужны вызывающему коду, чтобы сохранить запись
    в таблице refresh_tokens (для возможности отзыва при logout).
    """
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti, expires_at


def create_registration_token(phone: str) -> str:
    """
    Короткоживущий токен, подтверждающий, что владелец phone прошёл
    проверку SMS-кодом, но ещё не зарегистрирован. Используется между
    вызовами /auth/verify-code и /auth/register.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "phone": phone,
        "type": "registration",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_telegram_link_token(user_id: int) -> str:
    """
    Токен, зашитый в deep-link на бота (?start=<token>). Живёт недолго —
    пользователь обычно нажимает «Старт» сразу после генерации ссылки.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "telegram_link",
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Бросает JWTError, если токен невалиден, просрочен или подделан."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


__all__ = [
    "hash_code",
    "verify_code",
    "create_access_token",
    "create_refresh_token",
    "create_registration_token",
    "create_telegram_link_token",
    "decode_token",
    "JWTError",
]
