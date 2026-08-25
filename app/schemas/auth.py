from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

PHONE_PATTERN = r"^\+?\d{10,15}$"


class RequestCodeIn(BaseModel):
    phone: str = Field(..., examples=["+79991234567"])

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        v = v.strip().replace(" ", "").replace("-", "")
        import re
        if not re.match(PHONE_PATTERN, v):
            raise ValueError("Некорректный формат телефона")
        return v


class RequestCodeOut(BaseModel):
    request_id: str
    # Присутствует ТОЛЬКО в ENVIRONMENT=local — чтобы можно было
    # тестировать без реального SMS-провайдера. На проде это поле = None.
    debug_code: Optional[str] = None


class VerifyCodeIn(BaseModel):
    request_id: str
    code: str


class UserOut(BaseModel):
    id: int
    role: str
    name: str
    phone: str
    city: Optional[str] = None

    model_config = {"from_attributes": True}


class UserUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    city: Optional[str] = Field(default=None, max_length=255)


class TokenPairOut(BaseModel):
    status: Literal["logged_in"] = "logged_in"
    access_token: str
    refresh_token: str
    user: UserOut


class RegistrationRequiredOut(BaseModel):
    status: Literal["registration_required"] = "registration_required"
    registration_token: str


class RegisterIn(BaseModel):
    registration_token: str
    role: Literal["coach", "parent", "arena_admin"]
    name: str = Field(..., min_length=1, max_length=255)
    city: Optional[str] = None


class RefreshIn(BaseModel):
    refresh_token: str


class AccessTokenOut(BaseModel):
    access_token: str


class LogoutIn(BaseModel):
    refresh_token: str
