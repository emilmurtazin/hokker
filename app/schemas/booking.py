from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BookingIn(BaseModel):
    child_id: int


class BookingOut(BaseModel):
    id: int
    session_id: int
    player_id: int
    status: str
    invited_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
