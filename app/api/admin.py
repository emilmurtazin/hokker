"""
API панели администратора (отдельное desktop-приложение, не мобильный фронтенд).

Всё под префиксом /admin и защищено require_role("admin"). Библиотека упражнений
(/admin/exercises) уже реализована раньше в app/api/exercises.py — здесь не дублируется.

Модерация пользователей — через блокировку (is_blocked), а не удаление: удаление
каскадно унесло бы тренировки/записи/детей и т.д., это необратимо и не то, что
обычно нужно администратору. Заблокированный пользователь не может войти
(app/api/auth.py) и теряет доступ по уже выданному токену (app/api/deps.py).
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.bookings import _promote_next_waiting, _to_booking_out
from app.api.deps import require_role
from app.api.sessions import _affected_parents, _booked_count
from app.core.database import get_db
from app.models.arena import Arena
from app.models.booking import Booking
from app.models.coach import Coach
from app.models.coach_player import CoachPlayer
from app.models.enums import (
    BookingStatus,
    CoachPlayerStatus,
    ExerciseContentStatus,
    SlotRequestStatus,
    SlotStatus,
    UserRole,
)
from app.models.exercise import Exercise
from app.models.ice_slot import IceSlot
from app.models.player import Player
from app.models.slot_request import SlotRequest
from app.models.training_session import TrainingSession
from app.models.user import User
from app.schemas.admin import (
    AdminArenaListItem,
    AdminArenaOut,
    AdminArenaUpdateIn,
    AdminBookingListItem,
    AdminBookingRef,
    AdminChildOut,
    AdminCoachProfileOut,
    AdminCoachUpdateIn,
    AdminIceSlotOut,
    AdminSessionListItem,
    AdminSessionOut,
    AdminSlotRequestOut,
    AdminStatsOut,
    AdminUserListItem,
    AdminUserOut,
    AdminUserUpdateIn,
    Page,
    RegistrationsPoint,
    RoleCounts,
)
from app.services.formatting import session_title
from app.services.notifications import notify

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])


# --- Дашборд ---


@router.get("/stats", response_model=AdminStatsOut)
def get_stats(db: Session = Depends(get_db)):
    role_counts = dict(db.query(User.role, func.count(User.id)).group_by(User.role).all())
    users_blocked = db.query(func.count(User.id)).filter(User.is_blocked.is_(True)).scalar()

    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    reg_rows = (
        db.query(func.date(User.created_at), func.count(User.id))
        .filter(User.created_at >= thirty_days_ago)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
        .all()
    )

    booking_counts = dict(
        db.query(Booking.status, func.count(Booking.id)).group_by(Booking.status).all()
    )
    slot_counts = dict(
        db.query(IceSlot.status, func.count(IceSlot.id)).group_by(IceSlot.status).all()
    )

    return AdminStatsOut(
        users_total=sum(role_counts.values()),
        users_by_role=RoleCounts(
            parent=role_counts.get(UserRole.parent, 0),
            coach=role_counts.get(UserRole.coach, 0),
            arena_admin=role_counts.get(UserRole.arena_admin, 0),
            admin=role_counts.get(UserRole.admin, 0),
        ),
        users_blocked=users_blocked or 0,
        players_total=db.query(func.count(Player.id)).scalar(),
        coaches_visible=db.query(func.count(Coach.id)).filter(Coach.visible_in_search.is_(True)).scalar(),
        coaches_hidden=db.query(func.count(Coach.id)).filter(Coach.visible_in_search.is_(False)).scalar(),
        arenas_total=db.query(func.count(Arena.id)).scalar(),
        exercises_total=db.query(func.count(Exercise.id)).scalar(),
        exercises_draft=db.query(func.count(Exercise.id))
        .filter(Exercise.content_status == ExerciseContentStatus.draft)
        .scalar(),
        sessions_total=db.query(func.count(TrainingSession.id)).scalar(),
        sessions_upcoming=db.query(func.count(TrainingSession.id))
        .filter(TrainingSession.datetime_ >= now)
        .scalar(),
        bookings_total=sum(booking_counts.values()),
        bookings_confirmed=booking_counts.get(BookingStatus.confirmed, 0),
        bookings_waiting=booking_counts.get(BookingStatus.waiting, 0),
        ice_slots_total=sum(slot_counts.values()),
        ice_slots_available=slot_counts.get(SlotStatus.available, 0),
        ice_slots_booked=slot_counts.get(SlotStatus.booked, 0),
        slot_requests_pending=db.query(func.count(SlotRequest.id))
        .filter(SlotRequest.status == SlotRequestStatus.pending)
        .scalar(),
        registrations_last_30_days=[
            RegistrationsPoint(date=d, count=c) for d, c in reg_rows
        ],
    )


# --- Пользователи ---


@router.get("/users", response_model=Page[AdminUserListItem])
def list_users(
    role: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None, description="Поиск по имени или телефону"),
    is_blocked: Optional[bool] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if role:
        query = query.filter(User.role == UserRole(role))
    if is_blocked is not None:
        query = query.filter(User.is_blocked.is_(is_blocked))
    if search:
        like = f"%{search.strip()}%"
        query = query.filter((User.name.ilike(like)) | (User.phone.ilike(like)))

    total = query.count()
    rows = (
        query.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items: list[AdminUserListItem] = []
    for u in rows:
        item = AdminUserListItem.model_validate(u)
        if u.role == UserRole.parent:
            item.children_count = db.query(func.count(Player.id)).filter(Player.parent_id == u.id).scalar()
        elif u.role == UserRole.coach:
            item.active_students_count = (
                db.query(func.count(CoachPlayer.id))
                .filter(CoachPlayer.coach_id == u.id, CoachPlayer.status == CoachPlayerStatus.active)
                .scalar()
            )
        elif u.role == UserRole.arena_admin:
            arena = db.get(Arena, u.id)
            item.arena_name = arena.name if arena else None
        items.append(item)

    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/users/{user_id}", response_model=AdminUserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    children = []
    coach_profile = None
    arena_profile = None

    if user.role == UserRole.parent:
        children = [
            AdminChildOut(id=p.id, name=p.name, birth_date=p.birth_date, position=p.position.value)
            for p in db.query(Player).filter(Player.parent_id == user.id).all()
        ]
    elif user.role == UserRole.coach:
        coach = db.get(Coach, user.id)
        if coach:
            active_students = (
                db.query(func.count(CoachPlayer.id))
                .filter(CoachPlayer.coach_id == user.id, CoachPlayer.status == CoachPlayerStatus.active)
                .scalar()
            )
            sessions_count = (
                db.query(func.count(TrainingSession.id))
                .filter(TrainingSession.coach_id == user.id)
                .scalar()
            )
            coach_profile = AdminCoachProfileOut(
                specializations=[s.value for s in coach.specializations],
                experience_years=coach.experience_years,
                about=coach.about,
                age_groups=[a.value for a in (coach.age_groups or [])],
                visible_in_search=coach.visible_in_search,
                join_code=coach.join_code,
                active_students_count=active_students,
                sessions_count=sessions_count,
            )
    elif user.role == UserRole.arena_admin:
        arena = db.get(Arena, user.id)
        if arena:
            arena_profile = {
                "name": arena.name,
                "address": arena.address,
                "city": arena.city,
                "ice_size": arena.ice_size,
                "locker_rooms": arena.locker_rooms,
                "contact_phone": arena.contact_phone,
            }

    return AdminUserOut(
        id=user.id,
        role=user.role.value,
        name=user.name,
        phone=user.phone,
        city=user.city,
        telegram_linked=bool(user.telegram_chat_id),
        is_blocked=user.is_blocked,
        blocked_reason=user.blocked_reason,
        blocked_at=user.blocked_at,
        created_at=user.created_at,
        children=children,
        coach_profile=coach_profile,
        arena_profile=arena_profile,
    )


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: int,
    data: AdminUserUpdateIn,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.id == admin.id and data.is_blocked:
        raise HTTPException(status_code=400, detail="Нельзя заблокировать самого себя")

    updates = data.model_dump(exclude_unset=True)
    if "phone" in updates and updates["phone"] != user.phone:
        exists = db.query(User).filter(User.phone == updates["phone"]).first()
        if exists:
            raise HTTPException(status_code=400, detail="Этот номер уже занят другим пользователем")

    was_blocked = user.is_blocked
    for field, value in updates.items():
        setattr(user, field, value)
    if "is_blocked" in updates:
        user.blocked_at = datetime.now(timezone.utc) if updates["is_blocked"] else None
        if not updates["is_blocked"]:
            user.blocked_reason = None

    db.commit()
    db.refresh(user)
    return get_user(user_id, db)


@router.patch("/coaches/{coach_id}", response_model=AdminUserOut)
def update_coach(
    coach_id: int,
    data: AdminCoachUpdateIn,
    db: Session = Depends(get_db),
):
    coach = db.get(Coach, coach_id)
    if coach is None:
        raise HTTPException(status_code=404, detail="Тренер не найден")
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(coach, field, value)
    db.commit()
    return get_user(coach_id, db)


# --- Арены ---


@router.get("/arenas", response_model=list[AdminArenaListItem])
def list_arenas(search: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(Arena)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter((Arena.name.ilike(like)) | (Arena.city.ilike(like)))

    items = []
    for arena in query.order_by(Arena.name.asc()).all():
        admin_user = db.get(User, arena.id)
        slots_total = db.query(func.count(IceSlot.id)).filter(IceSlot.arena_id == arena.id).scalar()
        slots_available = (
            db.query(func.count(IceSlot.id))
            .filter(IceSlot.arena_id == arena.id, IceSlot.status == SlotStatus.available)
            .scalar()
        )
        items.append(
            AdminArenaListItem(
                id=arena.id,
                name=arena.name,
                city=arena.city,
                address=arena.address,
                admin_name=admin_user.name if admin_user else "—",
                admin_phone=admin_user.phone if admin_user else "—",
                is_blocked=admin_user.is_blocked if admin_user else False,
                slots_total=slots_total,
                slots_available=slots_available,
            )
        )
    return items


@router.get("/arenas/{arena_id}", response_model=AdminArenaOut)
def get_arena(arena_id: int, db: Session = Depends(get_db)):
    arena = db.get(Arena, arena_id)
    if arena is None:
        raise HTTPException(status_code=404, detail="Арена не найдена")
    admin_user = db.get(User, arena.id)
    return AdminArenaOut(
        id=arena.id,
        name=arena.name,
        address=arena.address,
        city=arena.city,
        ice_size=arena.ice_size,
        locker_rooms=arena.locker_rooms,
        contact_phone=arena.contact_phone,
        admin_name=admin_user.name if admin_user else "—",
        admin_phone=admin_user.phone if admin_user else "—",
        is_blocked=admin_user.is_blocked if admin_user else False,
    )


@router.patch("/arenas/{arena_id}", response_model=AdminArenaOut)
def update_arena(arena_id: int, data: AdminArenaUpdateIn, db: Session = Depends(get_db)):
    arena = db.get(Arena, arena_id)
    if arena is None:
        raise HTTPException(status_code=404, detail="Арена не найдена")
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(arena, field, value)
    db.commit()
    return get_arena(arena_id, db)


# --- Тренировки ---


@router.get("/sessions", response_model=Page[AdminSessionListItem])
def list_sessions(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    coach_id: Optional[int] = Query(default=None),
    type: Optional[str] = Query(default=None),
    visibility: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(TrainingSession)
    if date_from:
        query = query.filter(TrainingSession.datetime_ >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
    if date_to:
        query = query.filter(TrainingSession.datetime_ <= datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc))
    if coach_id:
        query = query.filter(TrainingSession.coach_id == coach_id)
    if type:
        query = query.filter(TrainingSession.type == type)
    if visibility:
        query = query.filter(TrainingSession.visibility == visibility)

    total = query.count()
    rows = (
        query.order_by(TrainingSession.datetime_.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for s in rows:
        coach = db.get(User, s.coach_id)
        items.append(
            AdminSessionListItem(
                id=s.id,
                type=s.type.value,
                visibility=s.visibility.value,
                datetime=s.datetime_,
                duration_minutes=s.duration_minutes,
                coach_id=s.coach_id,
                coach_name=coach.name if coach else "—",
                arena_name=s.arena_name,
                max_players=s.max_players,
                booked_count=_booked_count(db, s.id),
            )
        )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/sessions/{session_id}", response_model=AdminSessionOut)
def get_session(session_id: int, db: Session = Depends(get_db)):
    s = db.get(TrainingSession, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    coach = db.get(User, s.coach_id)

    bookings = []
    for b in db.query(Booking).filter(Booking.session_id == s.id).order_by(Booking.created_at.asc()).all():
        player = db.get(Player, b.player_id) if b.player_id else None
        parent = db.get(User, player.parent_id) if player else None
        bookings.append(
            AdminBookingRef(
                id=b.id,
                player_name=player.name if player else (b.manual_player_name or "—"),
                parent_name=parent.name if parent else None,
                parent_phone=parent.phone if parent else None,
                status=b.status.value,
            )
        )

    return AdminSessionOut(
        id=s.id,
        type=s.type.value,
        visibility=s.visibility.value,
        datetime=s.datetime_,
        duration_minutes=s.duration_minutes,
        coach_id=s.coach_id,
        coach_name=coach.name if coach else "—",
        arena_name=s.arena_name,
        max_players=s.max_players,
        booked_count=_booked_count(db, s.id),
        price=float(s.price) if s.price is not None else None,
        bookings=bookings,
    )


@router.post("/sessions/{session_id}/cancel", status_code=204)
def cancel_session(session_id: int, db: Session = Depends(get_db)):
    s = db.get(TrainingSession, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")

    title = session_title(s)
    parents = _affected_parents(db, session_id)
    coach = db.get(User, s.coach_id)

    db.delete(s)  # bookings удалятся каскадно
    db.commit()

    for parent in parents:
        notify("session_cancelled", parent, session_title=title)
    if coach:
        notify("session_cancelled", coach, session_title=title)
    return None


# --- Записи ---


@router.get("/bookings", response_model=Page[AdminBookingListItem])
def list_bookings(
    status: Optional[str] = Query(default=None),
    session_id: Optional[int] = Query(default=None),
    search: Optional[str] = Query(default=None, description="Поиск по имени ученика"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Booking)
    if status:
        query = query.filter(Booking.status == BookingStatus(status))
    if session_id:
        query = query.filter(Booking.session_id == session_id)

    total = query.count()
    rows = (
        query.order_by(Booking.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for b in rows:
        player = db.get(Player, b.player_id) if b.player_id else None
        player_name = player.name if player else (b.manual_player_name or "—")
        if search and search.strip().lower() not in player_name.lower():
            continue
        parent = db.get(User, player.parent_id) if player else None
        session = db.get(TrainingSession, b.session_id)
        items.append(
            AdminBookingListItem(
                id=b.id,
                status=b.status.value,
                session_id=b.session_id,
                session_title=session_title(session) if session else "—",
                session_datetime=session.datetime_ if session else b.created_at,
                player_name=player_name,
                parent_name=parent.name if parent else None,
                parent_phone=parent.phone if parent else None,
                created_at=b.created_at,
            )
        )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/bookings/{booking_id}/cancel", status_code=204)
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    was_confirmed = booking.status == BookingStatus.confirmed
    was_active = booking.status in (
        BookingStatus.pending,
        BookingStatus.confirmed,
        BookingStatus.waiting,
        BookingStatus.invited,
    )
    booking.status = BookingStatus.cancelled
    db.commit()

    session = db.get(TrainingSession, booking.session_id)
    player = db.get(Player, booking.player_id) if booking.player_id else None
    if was_active and session:
        coach = db.get(User, session.coach_id)
        notify(
            "booking_cancelled",
            coach,
            session_title=session_title(session),
            player_name=player.name if player else (booking.manual_player_name or "—"),
            path=f"/sessions/{session.id}",
        )

    if was_confirmed:
        _promote_next_waiting(db, booking.session_id)
    return None


# --- Лёд ---


@router.get("/ice-slots", response_model=list[AdminIceSlotOut])
def list_ice_slots(
    arena_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(IceSlot)
    if arena_id:
        query = query.filter(IceSlot.arena_id == arena_id)
    if status:
        query = query.filter(IceSlot.status == SlotStatus(status))
    if date_from:
        query = query.filter(IceSlot.date >= date_from)
    if date_to:
        query = query.filter(IceSlot.date <= date_to)

    items = []
    for slot in query.order_by(IceSlot.date.desc(), IceSlot.time_start.desc()).limit(500).all():
        arena = db.get(Arena, slot.arena_id)
        requested_by = None
        if slot.status == SlotStatus.booked:
            req = (
                db.query(SlotRequest)
                .filter(SlotRequest.slot_id == slot.id, SlotRequest.status == SlotRequestStatus.approved)
                .first()
            )
            if req:
                coach = db.get(User, req.coach_id)
                requested_by = coach.name if coach else None
        items.append(
            AdminIceSlotOut(
                id=slot.id,
                arena_id=slot.arena_id,
                arena_name=arena.name if arena else "—",
                date=slot.date,
                time_start=slot.time_start,
                time_end=slot.time_end,
                ice_type=slot.ice_type.value,
                status=slot.status.value,
                price=float(slot.price) if slot.price is not None else None,
                requested_by_coach_name=requested_by,
            )
        )
    return items


@router.get("/slot-requests", response_model=list[AdminSlotRequestOut])
def list_slot_requests(
    status: Optional[str] = Query(default=None),
    arena_id: Optional[int] = Query(default=None),
    coach_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(SlotRequest)
    if status:
        query = query.filter(SlotRequest.status == SlotRequestStatus(status))
    if coach_id:
        query = query.filter(SlotRequest.coach_id == coach_id)

    items = []
    for req in query.order_by(SlotRequest.created_at.desc()).limit(500).all():
        slot = db.get(IceSlot, req.slot_id)
        if slot is None or (arena_id and slot.arena_id != arena_id):
            continue
        arena = db.get(Arena, slot.arena_id)
        coach = db.get(User, req.coach_id)
        items.append(
            AdminSlotRequestOut(
                id=req.id,
                status=req.status.value,
                slot_id=req.slot_id,
                arena_name=arena.name if arena else "—",
                date=slot.date,
                time_start=slot.time_start,
                time_end=slot.time_end,
                coach_id=req.coach_id,
                coach_name=coach.name if coach else "—",
                coach_phone=coach.phone if coach else "—",
                created_at=req.created_at,
            )
        )
    return items
