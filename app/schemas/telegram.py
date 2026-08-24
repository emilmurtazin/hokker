from pydantic import BaseModel


class TelegramLinkOut(BaseModel):
    deep_link: str
