from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.arena import Arena
from app.models.enums import IceType, SlotRequestStatus, SlotStatus
from app.models.ice_slot import IceSlot
from app.models.slot_request import SlotRequest
from app.models.user import User
from app.schemas.arena import (
    ArenaProfileIn,
    ArenaProfileOut,
    IceSlotIn,
    IceSlotListOut,
    IceSlotOut,
    SlotRequestOut,
)
from app.services.notifications import notify

router = APIRouter(tags=["arenas"])


def _slot_out(db: Session, slot: IceSlot, arena: Arena, include_booking: bool = False) -> IceSlotOut:
    admin = db.get(User, arena.id)
    booked_by_name = None
    booked_by_phone = None

    if include_booking and slot.status == SlotStatus.booked:
        approved_request = (
            db.query(SlotRequest)
            .filter(SlotRequest.slot_id == slot.id, SlotRequest.status == SlotRequestStatus.approved)
            .first()
        )
        if approved_request:
            coach = db.get(User, approved_request.coach_id)
            if coach:
                booked_by_name = coach.name
                booked_by_phone = coach.phone

    return IceSlotOut(
        id=slot.id,
        arena_id=arena.id,
        arena_name=arena.name,
        arena_city=arena.city,
        arena_address=arena.address,
        arena_ice_size=arena.ice_size,
        arena_locker_rooms=arena.locker_rooms,
        arena_phone=arena.contact_phone or (admin.phone if admin else None),
        date=slot.date,
        time_start=slot.time_start,
        time_end=slot.time_end,
        ice_type=slot.ice_type.value,
        price=float(slot.price) if slot.price is not None else None,
        status=slot.status.value,
        booked_by_coach_name=booked_by_name,
        booked_by_coach_phone=booked_by_phone,
    )


def _slot_info_text(slot: IceSlot, arena: Arena) -> str:
    return (
        f"{arena.name}, {slot.date.strftime('%d.%m.%Y')} "
        f"{slot.time_start.strftime('%H:%M')}–{slot.time_end.strftime('%H:%M')}"
    )


# --- Профиль арены ---


@router.post("/arenas/me/profile", response_model=ArenaProfileOut)
def upsert_arena_profile(
    data: ArenaProfileIn,
    user: User = Depends(require_role("arena_admin")),
    db: Session = Depends(get_db),
):
    arena = db.get(Arena, user.id)
    if arena is None:
        arena = Arena(id=user.id)
        db.add(arena)

    arena.name = data.name
    arena.address = data.address
    arena.city = data.city
    arena.ice_size = data.ice_size
    arena.locker_rooms = data.locker_rooms
    arena.contact_phone = data.contact_phone
    db.commit()
    db.refresh(arena)

    return ArenaProfileOut(
        id=arena.id,
        name=arena.name,
        address=arena.address,
        city=arena.city,
        ice_size=arena.ice_size,
        locker_rooms=arena.locker_rooms,
        contact_phone=arena.contact_phone,
    )


@router.get("/arenas/me/profile", response_model=ArenaProfileOut)
def get_arena_profile(
    user: User = Depends(require_role("arena_admin")),
    db: Session = Depends(get_db),
):
    arena = db.get(Arena, user.id)
    if arena is None:
        raise HTTPException(status_code=404, detail="Профиль арены ещё не заполнен")
    return ArenaProfileOut(
        id=arena.id,
        name=arena.name,
        address=arena.address,
        city=arena.city,
        ice_size=arena.ice_size,
        locker_rooms=arena.locker_rooms,
        contact_phone=arena.contact_phone,
    )


# --- Слоты (администратор арены) ---


@router.post("/arenas/me/slots", response_model=IceSlotOut)
def publish_slot(
    data: IceSlotIn,
    user: User = Depends(require_role("arena_admin")),
    db: Session = Depends(get_db),
):
    arena = db.get(Arena, user.id)
    if arena is None:
        raise HTTPException(
            status_code=409, detail="Сначала заполните профиль арены (/arenas/me/profile)"
        )
    if data.time_end <= data.time_start:
        raise HTTPException(status_code=422, detail="Время окончания должно быть позже начала")

    slot = IceSlot(
        arena_id=arena.id,
        date=data.date,
        time_start=data.time_start,
        time_end=data.time_end,
        ice_type=IceType(data.ice_type),
        price=data.price,
        status=SlotStatus.available,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return _slot_out(db, slot, arena)


@router.get("/arenas/me/slots", response_model=list[IceSlotOut])
def my_slots(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    when: Optional[str] = Query(
        default="upcoming", description="'upcoming' (по умолчанию) или 'past'"
    ),
    user: User = Depends(require_role("arena_admin")),
    db: Session = Depends(get_db),
):
    from datetime import datetime

    arena = db.get(Arena, user.id)
    if arena is None:
        raise HTTPException(status_code=404, detail="Профиль арены ещё не заполнен")

    query = db.query(IceSlot).filter(IceSlot.arena_id == arena.id)
    if status_filter:
        query = query.filter(IceSlot.status == SlotStatus(status_filter))
    rows = query.order_by(IceSlot.date.asc(), IceSlot.time_start.asc()).all()

    now = datetime.now()
    if when == "past":
        rows = [s for s in rows if datetime.combine(s.date, s.time_start) < now]
    else:
        rows = [s for s in rows if datetime.combine(s.date, s.time_start) >= now]

    return [_slot_out(db, s, arena, include_booking=True) for s in rows]


@router.delete("/arenas/me/slots/{slot_id}", status_code=204)
def cancel_slot(
    slot_id: int,
    user: User = Depends(require_role("arena_admin")),
    db: Session = Depends(get_db),
):
    slot = db.get(IceSlot, slot_id)
    if slot is None or slot.arena_id != user.id:
        raise HTTPException(status_code=404, detail="Слот не найден")
    if slot.status != SlotStatus.available:
        raise HTTPException(
            status_code=409, detail="Можно отменить только слот в статусе available (нет активной заявки)"
        )
    slot.status = SlotStatus.cancelled
    db.commit()
    return None


# --- Заявки (администратор арены) ---


@router.get("/arenas/me/requests", response_model=list[SlotRequestOut])
def my_requests(
    status_filter: Optional[str] = Query(default="pending", alias="status"),
    user: User = Depends(require_role("arena_admin")),
    db: Session = Depends(get_db),
):
    arena = db.get(Arena, user.id)
    if arena is None:
        raise HTTPException(status_code=404, detail="Профиль арены ещё не заполнен")

    query = (
        db.query(SlotRequest)
        .join(IceSlot, IceSlot.id == SlotRequest.slot_id)
        .filter(IceSlot.arena_id == arena.id)
    )
    if status_filter:
        query = query.filter(SlotRequest.status == SlotRequestStatus(status_filter))
    rows = query.order_by(SlotRequest.created_at.asc()).all()

    out = []
    for req in rows:
        slot = db.get(IceSlot, req.slot_id)
        coach = db.get(User, req.coach_id)
        out.append(
            SlotRequestOut(
                id=req.id,
                slot=_slot_out(db, slot, arena),
                coach_id=req.coach_id,
                coach_name=coach.name if coach else None,
                status=req.status.value,
                created_at=req.created_at,
            )
        )
    return out


@router.post("/arena-requests/{request_id}/approve", response_model=SlotRequestOut)
def approve_request(
    request_id: int,
    user: User = Depends(require_role("arena_admin")),
    db: Session = Depends(get_db),
):
    req = db.get(SlotRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    slot = db.get(IceSlot, req.slot_id)
    if slot.arena_id != user.id:
        raise HTTPException(status_code=403, detail="Доступно только владельцу арены")
    if req.status != SlotRequestStatus.pending:
        raise HTTPException(status_code=409, detail="Заявка не ожидает решения")

    req.status = SlotRequestStatus.approved
    slot.status = SlotStatus.booked
    db.commit()
    db.refresh(req)

    arena = db.get(Arena, user.id)
    coach = db.get(User, req.coach_id)
    notify("ice_request_approved", coach, slot_info=_slot_info_text(slot, arena))

    return SlotRequestOut(
        id=req.id,
        slot=_slot_out(db, slot, arena),
        coach_id=req.coach_id,
        coach_name=coach.name,
        status=req.status.value,
        created_at=req.created_at,
    )


@router.post("/arena-requests/{request_id}/reject", response_model=SlotRequestOut)
def reject_request(
    request_id: int,
    user: User = Depends(require_role("arena_admin")),
    db: Session = Depends(get_db),
):
    req = db.get(SlotRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    slot = db.get(IceSlot, req.slot_id)
    if slot.arena_id != user.id:
        raise HTTPException(status_code=403, detail="Доступно только владельцу арены")
    if req.status != SlotRequestStatus.pending:
        raise HTTPException(status_code=409, detail="Заявка не ожидает решения")

    req.status = SlotRequestStatus.rejected
    slot.status = SlotStatus.available  # слот возвращается в каталог
    db.commit()
    db.refresh(req)

    arena = db.get(Arena, user.id)
    coach = db.get(User, req.coach_id)
    notify("ice_request_rejected", coach, slot_info=_slot_info_text(slot, arena))

    return SlotRequestOut(
        id=req.id,
        slot=_slot_out(db, slot, arena),
        coach_id=req.coach_id,
        coach_name=coach.name,
        status=req.status.value,
        created_at=req.created_at,
    )


# --- Каталог и заявки (тренер) ---


@router.get("/ice-slots", response_model=IceSlotListOut)
def ice_slots_catalog(
    city: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    district: Optional[str] = Query(
        default=None, description="Простой поиск по подстроке в адресе арены"
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(IceSlot, Arena).join(Arena, Arena.id == IceSlot.arena_id).filter(
        IceSlot.status == SlotStatus.available
    )
    if city:
        query = query.filter(Arena.city == city)
    if district:
        query = query.filter(Arena.address.ilike(f"%{district}%"))
    if date_from:
        query = query.filter(IceSlot.date >= date_from)
    if date_to:
        query = query.filter(IceSlot.date <= date_to)

    total = query.count()
    rows = query.order_by(IceSlot.date.asc(), IceSlot.time_start.asc()).offset(offset).limit(limit).all()
    return IceSlotListOut(
        items=[_slot_out(db, s, a) for s, a in rows], total=total, limit=limit, offset=offset
    )


@router.post("/ice-slots/{slot_id}/request", response_model=SlotRequestOut)
def submit_slot_request(
    slot_id: int,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    slot = db.get(IceSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Слот не найден")
    if slot.status != SlotStatus.available:
        raise HTTPException(status_code=409, detail="Слот уже занят или заблокирован другой заявкой")

    slot.status = SlotStatus.pending  # блокируем слот на время рассмотрения
    req = SlotRequest(slot_id=slot.id, coach_id=user.id, status=SlotRequestStatus.pending)
    db.add(req)
    db.commit()
    db.refresh(req)

    arena = db.get(Arena, slot.arena_id)
    admin = db.get(User, arena.id)
    notify("ice_request_new", admin, coach_name=user.name, slot_info=_slot_info_text(slot, arena))

    return SlotRequestOut(
        id=req.id,
        slot=_slot_out(db, slot, arena),
        coach_id=req.coach_id,
        coach_name=user.name,
        status=req.status.value,
        created_at=req.created_at,
    )


@router.get("/coaches/me/ice-requests", response_model=list[SlotRequestOut])
def my_ice_requests(
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(SlotRequest)
        .filter(SlotRequest.coach_id == user.id)
        .order_by(SlotRequest.created_at.desc())
        .all()
    )
    out = []
    for req in rows:
        slot = db.get(IceSlot, req.slot_id)
        arena = db.get(Arena, slot.arena_id)
        out.append(
            SlotRequestOut(
                id=req.id,
                slot=_slot_out(db, slot, arena),
                coach_id=req.coach_id,
                coach_name=user.name,
                status=req.status.value,
                created_at=req.created_at,
            )
        )
    return out


@router.post("/coaches/me/ice-requests/{request_id}/cancel", response_model=SlotRequestOut)
def cancel_ice_request(
    request_id: int,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    req = db.get(SlotRequest, request_id)
    if req is None or req.coach_id != user.id:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if req.status not in (SlotRequestStatus.pending, SlotRequestStatus.approved):
        raise HTTPException(status_code=409, detail="Эту заявку уже нельзя отменить")

    slot = db.get(IceSlot, req.slot_id)
    req.status = SlotRequestStatus.cancelled_by_coach
    slot.status = SlotStatus.available  # слот возвращается в каталог
    db.commit()
    db.refresh(req)

    arena = db.get(Arena, slot.arena_id)
    admin = db.get(User, arena.id)
    notify("ice_request_cancelled", admin, coach_name=user.name, slot_info=_slot_info_text(slot, arena))

    return SlotRequestOut(
        id=req.id,
        slot=_slot_out(db, slot, arena),
        coach_id=req.coach_id,
        coach_name=user.name,
        status=req.status.value,
        created_at=req.created_at,
    )
