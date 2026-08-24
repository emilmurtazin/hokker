from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

POSITIONS = Literal["forward", "defense", "goalie"]


class ChildIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    birth_date: date
    position: POSITIONS


class ChildUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    birth_date: Optional[date] = None
    position: Optional[POSITIONS] = None


class ChildOut(BaseModel):
    id: int
    name: str
    birth_date: date
    position: str
    parent_id: int

    model_config = {"from_attributes": True}
