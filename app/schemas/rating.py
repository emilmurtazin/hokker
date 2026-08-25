from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

SKILL = Literal["skating", "stickhandling", "shooting", "tactics", "discipline"]


class RatingEntryIn(BaseModel):
    player_id: int
    skill: SKILL
    score: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=1000)


class RatingsBulkIn(BaseModel):
    entries: List[RatingEntryIn]


class GroupRatingIn(BaseModel):
    """Одна оценка сразу всей группе (всем confirmed-записанным на тренировку)."""
    skill: SKILL
    score: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=1000)


class RatingOut(BaseModel):
    player_id: int
    player_name: str
    skill: SKILL
    score: int
    comment: Optional[str] = None
    updated_at: datetime


class SkillAverageOut(BaseModel):
    skill: SKILL
    average: float
    count: int


class ProgressPointOut(BaseModel):
    period: str  # "2026-W35" для недель, "2026-09" для месяцев
    skill: SKILL
    average: float


class ProgressOut(BaseModel):
    radar: List[SkillAverageOut]
    weekly: List[ProgressPointOut]
    monthly: List[ProgressPointOut]


class PlayerPassportOut(BaseModel):
    player_id: int
    name: str
    age: int
    position: str
    overall_average: Optional[float] = None
    radar: List[SkillAverageOut]
    total_sessions: int
    attendance_present: int
    attendance_total: int
