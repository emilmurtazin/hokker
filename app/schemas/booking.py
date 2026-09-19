from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class BookingIn(BaseModel):
    child_id: int


class ManualBookingIn(BaseModel):
    player_name: str = Field(..., min_length=1, max_length=255)


class BookingOut(BaseModel):
    id: int
    session_id: int
    player_id: Optional[int] = None
    player_name: Optional[str] = None
    player_age: Optional[int] = None
    player_position: Optional[str] = None
    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None
    status: str
    invited_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
