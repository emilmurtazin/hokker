from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

SPECIALIZATIONS = Literal["skating", "shooting", "off_ice", "goalie", "general"]


class CoachProfileIn(BaseModel):
    specialization: SPECIALIZATIONS
    experience_years: Optional[int] = Field(default=None, ge=0, le=60)
    about: Optional[str] = Field(default=None, max_length=2000)
    # через запятую, например "6-9,10-12,13+"
    age_groups: Optional[str] = Field(default=None, max_length=255)
    visible_in_search: bool = True


class CoachProfileOut(BaseModel):
    id: int
    name: str
    city: Optional[str] = None
    specialization: str
    experience_years: Optional[int] = None
    about: Optional[str] = None
    age_groups: Optional[str] = None
    visible_in_search: bool = True


class TrainingSessionShortOut(BaseModel):
    id: int
    type: str
    datetime: datetime
    max_players: int
    price: Optional[float] = None


class CoachCardOut(BaseModel):
    id: int
    name: str
    specialization: str
    experience_years: Optional[int] = None
    next_open_sessions: List[TrainingSessionShortOut]


class CoachCatalogOut(BaseModel):
    items: List[CoachCardOut]
    total: int
    limit: int
    offset: int
