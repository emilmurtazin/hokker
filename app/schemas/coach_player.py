from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


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


class MessageIn(BaseModel):
    text: str
