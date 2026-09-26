from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

SPECIALIZATION = Literal["ice", "off_ice", "shooting", "theory", "game", "goalie"]
AGE_GROUP = Literal["6-9", "10-12", "13+"]


class CoachProfileIn(BaseModel):
    specializations: List[SPECIALIZATION] = Field(..., min_length=1)
    experience_years: Optional[int] = Field(default=None, ge=0, le=60)
    about: Optional[str] = Field(default=None, max_length=2000)
    age_groups: List[AGE_GROUP] = Field(default_factory=list)
    visible_in_search: bool = True


class CoachProfileOut(BaseModel):
    id: int
    name: str
    city: Optional[str] = None
    specializations: List[str]
    experience_years: Optional[int] = None
    about: Optional[str] = None
    age_groups: List[str] = []
    visible_in_search: bool = True
    # Виден только самому тренеру (родителям — никогда): им делятся лично,
    # чтобы родитель мог добавить себя в клиенты через POST /coaches/join.
    # None в ЛЮБОМ ответе, кроме собственных /coaches/me/profile и regenerate —
    # публичный просмотр профиля (GET /coaches/{id}) их не заполняет.
    join_code: Optional[str] = None
    join_code_changed_at: Optional[datetime] = None


class TrainingSessionShortOut(BaseModel):
    id: int
    type: str
    datetime: datetime
    max_players: int
    price: Optional[float] = None


class CoachCardOut(BaseModel):
    id: int
    name: str
    specializations: List[str]
    experience_years: Optional[int] = None
    next_open_sessions: List[TrainingSessionShortOut]


class CoachCatalogOut(BaseModel):
    items: List[CoachCardOut]
    total: int
    limit: int
    offset: int

class CoachJoinPreviewOut(BaseModel):
    """То, что видит родитель после ввода кода — до выбора ребёнка и подтверждения."""

    id: int
    name: str
    city: Optional[str] = None
    specializations: List[str]
    experience_years: Optional[int] = None


class CoachJoinIn(BaseModel):
    code: str = Field(..., pattern=r"^\d{6}$")
    child_id: int

