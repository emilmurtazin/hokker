from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Все настройки приложения читаются из переменных окружения (.env).
    Никаких секретов не хранится в коде.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    REDIS_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""  # без @, например hokker_bot
    TELEGRAM_WEBHOOK_SECRET: str = ""  # см. app/api/telegram.py
    TELEGRAM_PROXY_URL: str = ""  # см. app/services/telegram.py — обход блокировки РКН

    # Список разрешённых доменов фронтенда через запятую, например:
    # "https://hokker-frontend.twc1.net,http://localhost:5173"
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    ENVIRONMENT: str = "local"

    # SMS / OTP
    SMS_PROVIDER: str = "console"  # "console" для разработки, "smsru" для продакшена
    SMSRU_API_ID: str = ""
    OTP_CODE_LENGTH: int = 4
    OTP_EXPIRE_MINUTES: int = 5
    OTP_MAX_REQUESTS_PER_WINDOW: int = 3
    OTP_WINDOW_MINUTES: int = 10


settings = Settings()
