"""
Абстракция отправки SMS. ConsoleSMSProvider — dev-заглушка (печатает код
в консоль). SMSRuProvider — реальная отправка через sms.ru.
"""

from abc import ABC, abstractmethod

import httpx

from app.core.config import settings


class SMSProvider(ABC):
    @abstractmethod
    def send(self, phone: str, code: str) -> None:
        """Отправляет SMS с кодом на указанный номер."""
        ...


class ConsoleSMSProvider(SMSProvider):
    """
    Заглушка для разработки: не отправляет реальную SMS, просто пишет
    код в логи контейнера. НЕ использовать в production.
    """

    def send(self, phone: str, code: str) -> None:
        print(f"[DEV SMS] Код для {phone}: {code}")


class SMSRuError(Exception):
    pass


class SMSRuProvider(SMSProvider):
    """
    Реальная отправка через https://sms.ru — простой GET-based API,
    один из самых распространённых у российских разработчиков.
    Регистрация и API-ключ: https://sms.ru/?panel=api
    """

    def send(self, phone: str, code: str) -> None:
        if not settings.SMSRU_API_ID:
            raise SMSRuError(
                "SMSRU_API_ID не задан в переменных окружения — SMS отправить нельзя"
            )
        response = httpx.get(
            "https://sms.ru/sms/send",
            params={
                "api_id": settings.SMSRU_API_ID,
                "to": phone,
                "msg": f"Код подтверждения 24hokker.ru: {code}",
                "json": 1,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()

        # sms.ru возвращает status_code=100 на верхнем уровне при успехе,
        # но у каждого номера в sms[] свой статус — проверяем оба уровня.
        if data.get("status") != "OK":
            raise SMSRuError(f"sms.ru вернул ошибку: {data}")

        sms_status = data.get("sms", {}).get(phone, {})
        if sms_status.get("status") != "OK":
            raise SMSRuError(f"sms.ru не смог отправить на {phone}: {sms_status}")


class SMSCError(Exception):
    pass


class SMSCProvider(SMSProvider):
    """
    Реальная отправка через https://smsc.ru — GET-based API.
    Авторизация: либо apikey (проще, один параметр), либо пара login+psw.
    Ключи и пароли: https://smsc.ru/passwords/
    """

    def send(self, phone: str, code: str) -> None:
        params = {
            "phones": phone,
            "mes": f"Код подтверждения {code}",
            "sender": "uvix",
            "fmt": 3,  # JSON-ответ
            "charset": "utf-8",
        }

        if settings.SMSC_API_KEY:
            params["apikey"] = settings.SMSC_API_KEY
        elif settings.SMSC_LOGIN and settings.SMSC_PASSWORD:
            params["login"] = settings.SMSC_LOGIN
            params["psw"] = settings.SMSC_PASSWORD
        else:
            raise SMSCError(
                "Не заданы учётные данные smsc.ru — нужен либо SMSC_API_KEY, "
                "либо пара SMSC_LOGIN + SMSC_PASSWORD"
            )

        response = httpx.get("https://smsc.ru/sys/send.php", params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        # При успехе smsc.ru возвращает {"id": ..., "cnt": ...} (fmt=3),
        # при ошибке — {"error": "текст", "error_code": N}.
        if "error" in data:
            raise SMSCError(
                f"smsc.ru не смог отправить SMS на {phone}: "
                f"[{data.get('error_code')}] {data.get('error')}"
            )


def get_sms_provider() -> SMSProvider:
    if settings.SMS_PROVIDER == "console":
        return ConsoleSMSProvider()
    if settings.SMS_PROVIDER == "smsru":
        return SMSRuProvider()
    if settings.SMS_PROVIDER == "smsc":
        return SMSCProvider()
    raise NotImplementedError(
        f"SMS-провайдер '{settings.SMS_PROVIDER}' ещё не реализован. "
        "Добавьте класс в app/services/sms.py и подключите здесь."
    )
