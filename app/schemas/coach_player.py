from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ParentLookupChildOut(BaseModel):
    id: int
    name: str
    birth_date: date
    position: str


class ParentLookupOut(BaseModel):
    parent_id: int
    parent_name: str
    parent_phone: str
    children: List[ParentLookupChildOut]


class CoachPlayerInviteIn(BaseModel):
    child_id: int


class AttendanceSummary(BaseModel):
    present: int = 0
    absent: int = 0
    sick: int = 0
    no_reason: int = 0


class CoachPlayerOut(BaseModel):
    id: int  # id связи coach_players
    coach_id: int
    coach_name: str
    player_id: int
    player_name: str
    birth_date: date
    age: int
    position: str
    status: str
    parent_id: int
    parent_name: str
    parent_phone: str
    attendance: AttendanceSummary
    sessions_count: int
    created_at: datetime
    # В каких группах тренера состоит ученик (id из GET /coaches/me/groups)
    group_ids: List[int] = []


class MessageIn(BaseModel):
    # Лимит Telegram — 4096 символов на сообщение, с запасом на приписку.
    text: str = Field(min_length=1, max_length=2000)


class AttendanceHistoryEntryOut(BaseModel):
    session_id: int
    session_type: str
    session_datetime: datetime
    status: Optional[str] = None  # None — тренировка была, но отметка не ставилась
