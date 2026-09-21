from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


# Адрес фронтенда по умолчанию (используется ботом, если APP_PUBLIC_URL не задан).
DEFAULT_PUBLIC_URL = "https://24hokker.ru"


def _origin_variants(url: str) -> list[str]:
    """
    'https://24hokker.ru/path' -> ['https://24hokker.ru', 'https://www.24hokker.ru'].
    Для localhost и IP-адресов двойник с www не добавляется.
    """
    parts = urlsplit((url or "").strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return []
    host = parts.hostname.lower()
    port = f":{parts.port}" if parts.port else ""
    variants = [f"{parts.scheme}://{host}{port}"]
    is_ip = all(chunk.isdigit() for chunk in host.split("."))
    if host != "localhost" and "." in host and not is_ip:
        twin = host[4:] if host.startswith("www.") else f"www.{host}"
        variants.append(f"{parts.scheme}://{twin}{port}")
    return variants


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
    APP_PUBLIC_URL: str = ""   # https://24hokker.ru — для кнопки «Открыть Хоккер»

    # Список разрешённых доменов фронтенда через запятую, например:
    # "https://hokker-frontend.twc1.net,http://localhost:5173"
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        """
        Домены, которым браузер разрешено обращаться к API:
          * всё из CORS_ORIGINS (без замыкающего «/»: браузер шлёт Origin без него,
            и запись «https://site.ru/» никогда не совпала бы);
          * адрес из APP_PUBLIC_URL и его двойник с «www.» / без него. Именно на этот
            адрес бот отправляет пользователей («Перейти на сайт», кнопки меню), поэтому
            он обязан быть разрешён. Иначе страница открывается, а любой запрос к API
            (например, «отправить SMS») браузер блокирует, и пользователь видит только
            «Не получилось отправить код».
        """
        origins = [o.strip().rstrip("/") for o in self.CORS_ORIGINS.split(",") if o.strip()]
        for extra in _origin_variants(self.APP_PUBLIC_URL or DEFAULT_PUBLIC_URL):
            if extra not in origins:
                origins.append(extra)
        return origins

    ENVIRONMENT: str = "local"

    # Часовой пояс, в котором пользователям показывается время в уведомлениях
    # Telegram (в БД всё хранится в UTC). Список: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
    APP_TIMEZONE: str = "Europe/Moscow"

    # Что открывает кнопка «Меню» слева от поля ввода в боте:
    #   commands — список команд (Расписание, Заявки, Профиль …) — по умолчанию;
    #   webapp   — сразу открывает приложение 24hokker.ru внутри Telegram.
    TELEGRAM_MENU_BUTTON: str = "commands"

    # Фоновые задачи: напоминания о тренировках и автоистечение приглашений
    # из листа ожидания (раньше истечение проверялось только когда родитель
    # сам нажимал «Подтвердить»).
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_INTERVAL_SECONDS: int = 60
    # За сколько часов до тренировки напоминать родителю (0 — не напоминать).
    REMINDER_HOURS_BEFORE: int = 3
    # «Тихие часы»: в это время (по APP_TIMEZONE) напоминания не отправляются.
    QUIET_HOURS_START: int = 22
    QUIET_HOURS_END: int = 8

    # SMS / OTP
    SMS_PROVIDER: str = "console"  # "console" для разработки, "smsru" для продакшена
    SMSRU_API_ID: str = ""
    # smsc.ru — либо apikey, либо пара login+password (см. https://smsc.ru/passwords/)
    SMSC_API_KEY: str = ""
    SMSC_LOGIN: str = ""
    SMSC_PASSWORD: str = ""
    OTP_CODE_LENGTH: int = 4
    OTP_EXPIRE_MINUTES: int = 5
    OTP_MAX_REQUESTS_PER_WINDOW: int = 3
    OTP_WINDOW_MINUTES: int = 10
    # Дежурный код, подходящий для входа на ЛЮБОЙ номер телефона — нужен для
    # прохождения проверки в App Store/Google Play и для тестирования.
    # ВАЖНО: пока это значение не пустое, кто угодно, зная номер телефона
    # пользователя, может войти в его аккаунт этим кодом. Выключить — оставить
    # пустую строку.
    MASTER_OTP_CODE: str = "2808"


settings = Settings()
