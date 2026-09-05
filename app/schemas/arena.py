from datetime import date, datetime, time
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

ICE_TYPE = Literal["full", "half", "third"]


class ArenaProfileIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=255)
    ice_size: Optional[str] = Field(default=None, max_length=100)
    locker_rooms: Optional[int] = Field(default=None, ge=0)
    contact_phone: Optional[str] = Field(default=None, max_length=20)


class ArenaProfileOut(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    ice_size: Optional[str] = None
    locker_rooms: Optional[int] = None
    contact_phone: Optional[str] = None


class IceSlotIn(BaseModel):
    date: date
    time_start: time
    time_end: time
    ice_type: ICE_TYPE
    price: Optional[float] = Field(default=None, ge=0)


class IceSlotOut(BaseModel):
    id: int
    arena_id: int
    arena_name: str
    arena_city: Optional[str] = None
    arena_address: Optional[str] = None
    arena_ice_size: Optional[str] = None
    arena_locker_rooms: Optional[int] = None
    # Контакт для тренера — сначала явно указанный contact_phone арены,
    # если не задан — номер, которым администратор входит в приложение.
    arena_phone: Optional[str] = None
    date: date
    time_start: time
    time_end: time
    ice_type: ICE_TYPE
    price: Optional[float] = None
    status: str
    # Заполняется только для владельца арены — кто забронировал этот слот.
    booked_by_coach_name: Optional[str] = None
    booked_by_coach_phone: Optional[str] = None


class IceSlotListOut(BaseModel):
    items: List[IceSlotOut]
    total: int
    limit: int
    offset: int


class SlotRequestOut(BaseModel):
    id: int
    slot: IceSlotOut
    coach_id: int
    coach_name: Optional[str] = None
    status: str
    created_at: datetime
