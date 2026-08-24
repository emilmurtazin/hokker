from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

SESSION_TYPES = Literal["ice", "off_ice", "shooting", "theory", "game"]
SESSION_VISIBILITY = Literal["open", "closed"]


class TrainingSessionIn(BaseModel):
    type: SESSION_TYPES
    visibility: SESSION_VISIBILITY
    datetime: datetime
    arena_name: Optional[str] = Field(default=None, max_length=255)
    max_players: int = Field(..., ge=1, le=100)

    @model_validator(mode="after")
    def check_future_datetime(self):
        # Сравнение с учётом таймзоны — datetime от клиента должен быть tz-aware
        if self.datetime.tzinfo is None:
            raise ValueError("datetime должен содержать таймзону")
        return self


class TrainingSessionOut(BaseModel):
    id: int
    coach_id: int
    type: str
    visibility: str
    datetime: datetime
    arena_name: Optional[str] = None
    max_players: int
    booked_count: int = 0

    model_config = {"from_attributes": True}


class TrainingSessionListOut(BaseModel):
    items: List[TrainingSessionOut]
    total: int
    limit: int
    offset: int
