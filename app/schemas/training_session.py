from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

SESSION_TYPES = Literal["ice", "off_ice", "shooting", "theory", "game", "goalie"]
SESSION_VISIBILITY = Literal["open", "closed"]


class TrainingSessionIn(BaseModel):
    type: SESSION_TYPES
    visibility: SESSION_VISIBILITY
    datetime: datetime
    duration_minutes: int = Field(default=60, ge=15, le=480)
    arena_name: Optional[str] = Field(default=None, max_length=255)
    max_players: int = Field(..., ge=1, le=100)
    price: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_future_datetime(self):
        # Сравнение с учётом таймзоны — datetime от клиента должен быть tz-aware
        if self.datetime.tzinfo is None:
            raise ValueError("datetime должен содержать таймзону")
        if self.datetime < datetime.now(self.datetime.tzinfo):
            raise ValueError("Нельзя создать тренировку в прошлом")
        return self


class TrainingSessionOut(BaseModel):
    id: int
    coach_id: int
    type: str
    visibility: str
    datetime: datetime
    duration_minutes: int
    arena_name: Optional[str] = None
    max_players: int
    price: Optional[float] = None
    booked_count: int = 0

    model_config = {"from_attributes": True}


class TrainingSessionFeedOut(TrainingSessionOut):
    """То же самое + имя тренера — для общей ленты тренировок (не через профиль)."""
    coach_name: str


class TrainingSessionListOut(BaseModel):
    items: List[TrainingSessionOut]
    total: int
    limit: int
    offset: int


class TrainingSessionFeedListOut(BaseModel):
    items: List[TrainingSessionFeedOut]
    total: int
    limit: int
    offset: int
