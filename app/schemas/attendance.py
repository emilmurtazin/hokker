from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

ATTENDANCE_STATUS = Literal["present", "absent", "sick", "no_reason"]


class AttendanceMarkIn(BaseModel):
    player_id: int
    status: ATTENDANCE_STATUS


class AttendanceBulkIn(BaseModel):
    """Отметить сразу несколько детей одним запросом."""
    marks: List[AttendanceMarkIn]


class AttendanceOut(BaseModel):
    player_id: int
    player_name: str
    status: Optional[ATTENDANCE_STATUS] = None  # None — ещё не отмечено
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
