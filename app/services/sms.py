"""
Абстракция отправки SMS. Сейчас есть только dev-заглушка (печатает код
в консоль контейнера). Когда подключите реального провайдера
(например, SMS.ru) — добавьте новый класс ниже и одну строку в get_sms_provider().
"""

from abc import ABC, abstractmethod

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


# Пример того, как будет выглядеть реальный провайдер (не реализован):
#
# class SMSRuProvider(SMSProvider):
#     def send(self, phone: str, code: str) -> None:
#         response = httpx.get(
#             "https://sms.ru/sms/send",
#             params={
#                 "api_id": settings.SMSRU_API_KEY,
#                 "to": phone,
#                 "msg": f"Код подтверждения ХОККЕР: {code}",
#                 "json": 1,
#             },
#         )
#         response.raise_for_status()


def get_sms_provider() -> SMSProvider:
    if settings.SMS_PROVIDER == "console":
        return ConsoleSMSProvider()
    raise NotImplementedError(
        f"SMS-провайдер '{settings.SMS_PROVIDER}' ещё не реализован. "
        "Добавьте класс в app/services/sms.py и подключите здесь."
    )
