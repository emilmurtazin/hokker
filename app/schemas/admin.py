from datetime import date, datetime, time
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# --- Дашборд ---


class RoleCounts(BaseModel):
    parent: int = 0
    coach: int = 0
    arena_admin: int = 0
    admin: int = 0


class RegistrationsPoint(BaseModel):
    date: date
    count: int


class AdminStatsOut(BaseModel):
    users_total: int
    users_by_role: RoleCounts
    users_blocked: int
    players_total: int
    coaches_visible: int
    coaches_hidden: int
    arenas_total: int
    exercises_total: int
    exercises_draft: int
    sessions_total: int
    sessions_upcoming: int
    bookings_total: int
    bookings_confirmed: int
    bookings_waiting: int
    ice_slots_total: int
    ice_slots_available: int
    ice_slots_booked: int
    slot_requests_pending: int
    registrations_last_30_days: list[RegistrationsPoint]


# --- Пользователи ---


class AdminUserListItem(BaseModel):
    id: int
    role: str
    name: str
    phone: str
    city: Optional[str] = None
    is_blocked: bool
    created_at: datetime
    # заполняется только для соответствующей роли
    children_count: Optional[int] = None
    active_students_count: Optional[int] = None
    arena_name: Optional[str] = None

    model_config = {"from_attributes": True}


class AdminChildOut(BaseModel):
    id: int
    name: str
    birth_date: date
    position: str


class AdminCoachProfileOut(BaseModel):
    specializations: list[str]
    experience_years: Optional[int] = None
    about: Optional[str] = None
    age_groups: list[str] = []
    visible_in_search: bool
    join_code: str
    active_students_count: int
    sessions_count: int


class AdminArenaProfileOut(BaseModel):
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    ice_size: Optional[str] = None
    locker_rooms: Optional[int] = None
    contact_phone: Optional[str] = None


class AdminUserOut(BaseModel):
    id: int
    role: str
    name: str
    phone: str
    city: Optional[str] = None
    telegram_linked: bool
    is_blocked: bool
    blocked_reason: Optional[str] = None
    blocked_at: Optional[datetime] = None
    created_at: datetime
    children: list[AdminChildOut] = []
    coach_profile: Optional[AdminCoachProfileOut] = None
    arena_profile: Optional[AdminArenaProfileOut] = None


class AdminUserUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    city: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, min_length=10, max_length=20)
    is_blocked: Optional[bool] = None
    blocked_reason: Optional[str] = Field(default=None, max_length=500)


class AdminCoachUpdateIn(BaseModel):
    visible_in_search: Optional[bool] = None


# --- Арены ---


class AdminArenaListItem(BaseModel):
    id: int
    name: str
    city: Optional[str] = None
    address: Optional[str] = None
    admin_name: str
    admin_phone: str
    is_blocked: bool
    slots_total: int
    slots_available: int


class AdminArenaOut(AdminArenaProfileOut):
    id: int
    admin_name: str
    admin_phone: str
    is_blocked: bool


class AdminArenaUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=255)
    ice_size: Optional[str] = Field(default=None, max_length=100)
    locker_rooms: Optional[int] = None
    contact_phone: Optional[str] = Field(default=None, max_length=20)


# --- Тренировки и записи ---


class AdminSessionListItem(BaseModel):
    id: int
    type: str
    visibility: str
    datetime: datetime
    duration_minutes: int
    coach_id: int
    coach_name: str
    arena_name: Optional[str] = None
    max_players: int
    booked_count: int


class AdminBookingRef(BaseModel):
    id: int
    player_name: str
    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None
    status: str


class AdminSessionOut(AdminSessionListItem):
    price: Optional[float] = None
    bookings: list[AdminBookingRef] = []


class AdminBookingListItem(BaseModel):
    id: int
    status: str
    session_id: int
    session_title: str
    session_datetime: datetime
    player_name: str
    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None
    created_at: datetime


# --- Лёд ---


class AdminIceSlotOut(BaseModel):
    id: int
    arena_id: int
    arena_name: str
    date: date
    time_start: time
    time_end: time
    ice_type: str
    status: str
    price: Optional[float] = None
    requested_by_coach_name: Optional[str] = None


class AdminSlotRequestOut(BaseModel):
    id: int
    status: str
    slot_id: int
    arena_name: str
    date: date
    time_start: time
    time_end: time
    coach_id: int
    coach_name: str
    coach_phone: str
    created_at: datetime
