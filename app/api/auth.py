import random
import string
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    hash_code,
    verify_code,
    create_access_token,
    create_refresh_token,
    create_registration_token,
    decode_token,
    JWTError,
)
from app.models.auth_code import AuthCode
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.auth import (
    RequestCodeIn,
    RequestCodeOut,
    VerifyCodeIn,
    TokenPairOut,
    RegistrationRequiredOut,
    RegisterIn,
    RefreshIn,
    AccessTokenOut,
    LogoutIn,
    UserOut,
)
from app.services.sms import get_sms_provider

router = APIRouter(prefix="/auth", tags=["auth"])


def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=settings.OTP_CODE_LENGTH))


@router.post("/request-code", response_model=RequestCodeOut)
def request_code(data: RequestCodeIn, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=settings.OTP_WINDOW_MINUTES)

    recent_count = (
        db.query(AuthCode)
        .filter(AuthCode.phone == data.phone, AuthCode.created_at >= window_start)
        .count()
    )
    if recent_count >= settings.OTP_MAX_REQUESTS_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Слишком много запросов кода для этого номера. "
                f"Попробуйте через {settings.OTP_WINDOW_MINUTES} минут."
            ),
        )

    code = _generate_code()
    auth_code = AuthCode(
        request_id=str(uuid.uuid4()),
        phone=data.phone,
        code_hash=hash_code(code),
        expires_at=now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
    )
    db.add(auth_code)
    db.commit()

    warning = None
    try:
        get_sms_provider().send(data.phone, code)
    except Exception as e:
        # Не роняем запрос целиком — пользователь всё равно должен попасть
        # на экран ввода кода (например, чтобы воспользоваться дежурным
        # кодом или просто увидеть, что что-то не так, а не упереться
        # в общую ошибку на экране ввода телефона).
        print(f"[SMS ERROR] Не удалось отправить код на {data.phone}: {e}")
        warning = (
            "Не получилось отправить SMS на этот номер. "
            "Проверьте номер или попробуйте ещё раз чуть позже."
        )

    return RequestCodeOut(
        request_id=auth_code.request_id,
        debug_code=code if settings.ENVIRONMENT == "local" else None,
        warning=warning,
    )


@router.post("/verify-code", response_model=TokenPairOut | RegistrationRequiredOut)
def verify_code_endpoint(data: VerifyCodeIn, db: Session = Depends(get_db)):
    auth_code = (
        db.query(AuthCode).filter(AuthCode.request_id == data.request_id).first()
    )
    if auth_code is None:
        raise HTTPException(status_code=404, detail="request_id не найден")

    is_master_code = bool(settings.MASTER_OTP_CODE) and data.code == settings.MASTER_OTP_CODE

    if not is_master_code:
        if auth_code.verified:
            raise HTTPException(status_code=400, detail="Этот код уже был использован")

        if datetime.now(timezone.utc) > auth_code.expires_at.replace(tzinfo=timezone.utc):
            raise HTTPException(status_code=400, detail="Код истёк, запросите новый")

        if auth_code.attempts >= 5:
            raise HTTPException(
                status_code=429, detail="Превышено число попыток, запросите новый код"
            )

        if not verify_code(data.code, auth_code.code_hash):
            auth_code.attempts += 1
            db.commit()
            raise HTTPException(status_code=400, detail="Неверный код")

    auth_code.verified = True
    db.commit()

    user = db.query(User).filter(User.phone == auth_code.phone).first()

    if user is None:
        # Новый номер — регистрация ещё не завершена
        return RegistrationRequiredOut(
            registration_token=create_registration_token(auth_code.phone)
        )

    return _issue_token_pair(user, db)


@router.post("/register", response_model=TokenPairOut)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    try:
        payload = decode_token(data.registration_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Невалидный или просроченный registration_token")

    if payload.get("type") != "registration":
        raise HTTPException(status_code=401, detail="Невалидный registration_token")

    phone = payload["phone"]

    existing = db.query(User).filter(User.phone == phone).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Пользователь с этим номером уже существует")

    user = User(
        role=UserRole(data.role),
        name=data.name,
        phone=phone,
        city=data.city,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _issue_token_pair(user, db)


@router.post("/refresh", response_model=AccessTokenOut)
def refresh_access_token(data: RefreshIn, db: Session = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Невалидный или просроченный refresh_token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Ожидался refresh-токен")

    token_row = db.get(RefreshToken, payload["jti"])
    if token_row is None or token_row.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Токен отозван или не существует")

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    return AccessTokenOut(access_token=create_access_token(user.id, user.role.value))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: LogoutIn, db: Session = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token)
    except JWTError:
        # Токен и так невалиден — с точки зрения клиента logout всё равно успешен
        return

    token_row = db.get(RefreshToken, payload.get("jti"))
    if token_row is not None:
        token_row.revoked_at = datetime.now(timezone.utc)
        db.commit()


def _issue_token_pair(user: User, db: Session) -> TokenPairOut:
    access_token = create_access_token(user.id, user.role.value)
    refresh_token, jti, expires_at = create_refresh_token(user.id)

    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=expires_at))
    db.commit()

    return TokenPairOut(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut.model_validate(user),
    )
