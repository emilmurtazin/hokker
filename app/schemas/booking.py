from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BookingIn(BaseModel):
    child_id: int


class BookingOut(BaseModel):
    id: int
    session_id: int
    player_id: int
    player_name: Optional[str] = None
    player_age: Optional[int] = None
    player_position: Optional[str] = None
    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None
    status: str
    invited_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
