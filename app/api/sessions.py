from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_user, require_role
from app.core.database import get_db
from app.models.booking import Booking
from app.models.client_group import SessionGroup
from app.models.arena import Arena
from app.models.coach import Coach
from app.models.enums import (
    BookingStatus,
    ExerciseAgeGroup,
    SessionType,
    SessionVisibility,
    Specialization,
)
from app.models.player import Player
from app.models.training_session import TrainingSession
from app.models.user import User
from app.schemas.client_group import SessionGroupsIn
from app.schemas.training_session import (
    GroupRefOut,
    TrainingSessionIn,
    TrainingSessionOut,
    TrainingSessionListOut,
    TrainingSessionFeedOut,
    TrainingSessionFeedListOut,
)
from app.services.access import (
    closed_session_open_to_parent,
    parent_can_view_session,
    session_groups,
    validated_group_ids,
)
from app.services.formatting import session_info, session_title as _session_title
from app.services.notifications import notify

router = APIRouter(tags=["sessions"])


def _booked_count(db: Session, session_id: int) -> int:
    """Сколько мест реально занято (только confirmed — waiting/invited в лимит не входят)."""
    return (
        db.query(func.count(Booking.id))
        .filter(Booking.session_id == session_id, Booking.status == BookingStatus.confirmed)
        .scalar()
    )


# Статусы, при которых у родителя «живая» запись: об изменении/отмене тренировки
# нужно сообщить всем им (rejected/cancelled/expired — уже не интересно).
_ACTIVE_BOOKING_STATUSES = [
    BookingStatus.confirmed,
    BookingStatus.waiting,
    BookingStatus.invited,
    BookingStatus.pending,
]


def _affected_parents(db: Session, session_id: int) -> list[User]:
    """
    Родители, у которых есть активная запись на тренировку — по одному разу
    (если двое детей одного родителя записаны на одну тренировку, сообщение одно).
    Записи без player_id (ученик, добавленный тренером вручную, без аккаунта) пропускаем:
    у них нет родителя в приложении, уведомлять некого.
    """
    rows = (
        db.query(User)
        .join(Player, Player.parent_id == User.id)
        .join(Booking, Booking.player_id == Player.id)
        .filter(
            Booking.session_id == session_id,
            Booking.status.in_(_ACTIVE_BOOKING_STATUSES),
        )
        .distinct()
        .all()
    )
    return rows


def _set_session_groups(db: Session, session: TrainingSession, group_ids: list[int]) -> None:
    """Заменяет список групп тренировки. Для открытой тренировки группы не хранятся."""
    db.query(SessionGroup).filter(SessionGroup.session_id == session.id).delete()
    if session.visibility == SessionVisibility.closed:
        db.add_all(SessionGroup(session_id=session.id, group_id=g) for g in group_ids)


def _to_out(db: Session, s: TrainingSession, with_groups: bool = False) -> TrainingSessionOut:
    arena = db.get(Arena, s.arena_id) if s.arena_id else None
    coach = db.get(User, s.coach_id)
    return TrainingSessionOut(
        id=s.id,
        coach_id=s.coach_id,
        type=s.type.value,
        visibility=s.visibility.value,
        datetime=s.datetime_,
        duration_minutes=s.duration_minutes,
        arena_name=s.arena_name,
        arena_address=arena.address if arena else None,
        coach_name=coach.name if coach else None,
        coach_phone=coach.phone if coach else None,
        max_players=s.max_players,
        price=float(s.price) if s.price is not None else None,
        booked_count=_booked_count(db, s.id),
        groups=[GroupRefOut(id=g.id, name=g.name) for g in session_groups(db, s.id)] if with_groups else [],
    )


@router.get("/sessions", response_model=TrainingSessionFeedListOut)
def sessions_feed(
    city: str = Query(..., description="Город — обязательный фильтр"),
    type: Optional[str] = Query(default=None, alias="type"),
    specialization: Optional[str] = Query(
        default=None, description="Фильтр по специализации тренера — как в каталоге тренеров"
    ),
    age_group: Optional[str] = Query(
        default=None, description="Фильтр по возрастной группе тренера — как в каталоге тренеров"
    ),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    Общая лента будущих тренировок — альтернатива поиску через конкретный профиль
    тренера. Поддерживает те же фильтры категорий, что и каталог тренеров
    (специализация, возраст).

    Всем видны открытые тренировки тренеров города. Авторизованному родителю к ним
    добавляются закрытые тренировки, доступные его детям (ученик тренера и, если у
    тренировки выбраны группы, состоит в одной из них). Город для закрытых не
    ограничивает: это тренировки «своего» тренера, где бы он ни жил.
    """
    open_clause = and_(
        TrainingSession.visibility == SessionVisibility.open,
        User.city == city,
        Coach.visible_in_search.is_(True),
    )
    if user is not None and user.role.value == "parent":
        visible_clause = or_(open_clause, closed_session_open_to_parent(user.id))
    else:
        visible_clause = open_clause
    query = (
        db.query(TrainingSession, User.name)
        .join(User, User.id == TrainingSession.coach_id)
        .join(Coach, Coach.id == TrainingSession.coach_id)
        .filter(
            visible_clause,
            TrainingSession.datetime_ >= datetime.now(timezone.utc),
        )
    )
    if type:
        query = query.filter(TrainingSession.type == SessionType(type))
    if specialization:
        query = query.filter(Coach.specializations.any(Specialization(specialization)))
    if age_group:
        query = query.filter(Coach.age_groups.any(ExerciseAgeGroup(age_group)))
    if date_from:
        query = query.filter(TrainingSession.datetime_ >= date_from)
    if date_to:
        query = query.filter(TrainingSession.datetime_ <= date_to)

    total = query.count()
    rows = query.order_by(TrainingSession.datetime_.asc()).offset(offset).limit(limit).all()

    items = [TrainingSessionFeedOut(**_to_out(db, s).model_dump()) for s, _ in rows]
    return TrainingSessionFeedListOut(items=items, total=total, limit=limit, offset=offset)


@router.post("/sessions", response_model=TrainingSessionOut)
def create_session(
    data: TrainingSessionIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    group_ids = validated_group_ids(db, user.id, data.group_ids)
    session = TrainingSession(
        coach_id=user.id,
        type=SessionType(data.type),
        visibility=SessionVisibility(data.visibility),
        datetime_=data.datetime,
        duration_minutes=data.duration_minutes,
        arena_id=data.arena_id,
        arena_name=data.arena_name,
        max_players=data.max_players,
        price=data.price,
    )
    db.add(session)
    db.flush()  # нужен session.id для связей с группами
    _set_session_groups(db, session, group_ids)
    db.commit()
    db.refresh(session)
    return _to_out(db, session, with_groups=True)


@router.get("/sessions/{session_id}", response_model=TrainingSessionOut)
def get_session(
    session_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    session = db.get(TrainingSession, session_id)
    # Закрытую тренировку видят только тренер, допущенные родители и записанные на неё.
    # Всем остальным — «не найдена», а не «нет доступа»: не подтверждаем, что она существует.
    if session is None or not parent_can_view_session(db, session, user):
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    return _to_out(db, session, with_groups=user is not None and user.id == session.coach_id)


@router.patch("/sessions/{session_id}", response_model=TrainingSessionOut)
def update_session(
    session_id: int,
    data: TrainingSessionIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    session = db.get(TrainingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    if session.coach_id != user.id:
        raise HTTPException(status_code=403, detail="Можно редактировать только свои тренировки")

    old_info = session_info(session)
    group_ids = validated_group_ids(db, user.id, data.group_ids) if data.group_ids is not None else None

    session.type = SessionType(data.type)
    session.visibility = SessionVisibility(data.visibility)
    session.datetime_ = data.datetime
    session.duration_minutes = data.duration_minutes
    session.arena_name = data.arena_name
    session.max_players = data.max_players
    session.price = data.price
    if group_ids is not None or session.visibility == SessionVisibility.open:
        _set_session_groups(db, session, group_ids or [])  # открытая: группы снимаются
    db.commit()
    db.refresh(session)

    # Меняется только цена/лимит мест — родителям это не важно. А вот перенос
    # времени, смена места, типа или длительности — важно: без уведомления
    # люди приедут в старое время.
    new_info = session_info(session)
    if new_info != old_info:
        for parent in _affected_parents(db, session.id):
            notify("session_updated", parent, old_info=old_info, new_info=new_info)

    return _to_out(db, session, with_groups=True)


@router.put("/sessions/{session_id}/groups", response_model=TrainingSessionOut)
def set_session_groups(
    session_id: int,
    data: SessionGroupsIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    """Меняет, каким группам доступна закрытая тренировка (пустой список — всем ученикам)."""
    session = db.get(TrainingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    if session.coach_id != user.id:
        raise HTTPException(status_code=403, detail="Можно редактировать только свои тренировки")
    if session.visibility != SessionVisibility.closed:
        raise HTTPException(status_code=409, detail="Группы задаются только для закрытых тренировок")
    _set_session_groups(db, session, validated_group_ids(db, user.id, data.group_ids))
    db.commit()
    return _to_out(db, session, with_groups=True)


@router.delete("/sessions/{session_id}", status_code=204)
def cancel_session(
    session_id: int,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    session = db.get(TrainingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    if session.coach_id != user.id:
        raise HTTPException(status_code=403, detail="Можно отменять только свои тренировки")

    # Уведомляем всех, у кого была активная запись или бронь листа ожидания —
    # до удаления, пока ещё видим их bookings. Раньше здесь падало с 500,
    # если на тренировке был ученик, добавленный тренером вручную (без player_id).
    title = _session_title(session)
    parents = _affected_parents(db, session_id)

    db.delete(session)  # bookings удалятся каскадно (ondelete=CASCADE)
    db.commit()

    # Уведомления — после успешного commit: если удаление не удалось,
    # родители не получат ложное «тренировка отменена».
    for parent in parents:
        notify("session_cancelled", parent, session_title=title)
    return None


@router.get("/coaches/me/sessions", response_model=TrainingSessionListOut)
def my_sessions(
    visibility: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    """Все свои тренировки — и open, и closed — видит только сам тренер."""
    query = db.query(TrainingSession).filter(TrainingSession.coach_id == user.id)
    if visibility:
        query = query.filter(TrainingSession.visibility == SessionVisibility(visibility))

    total = query.count()
    rows = query.order_by(TrainingSession.datetime_.asc()).offset(offset).limit(limit).all()
    return TrainingSessionListOut(
        items=[_to_out(db, s, with_groups=True) for s in rows], total=total, limit=limit, offset=offset
    )


# ВАЖНО: параметризованные роуты /coaches/{coach_id}/... регистрируются
# ПОСЛЕ литеральных /coaches/me/... — иначе FastAPI попытается матчить
# "me" как coach_id и упадёт с 422 вместо вызова правильного хендлера.


@router.get("/coaches/{coach_id}/sessions", response_model=TrainingSessionListOut)
def coach_sessions_public(
    coach_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Публичный список тренировок тренера (без авторизации) — только open.
    Для авторизованного родителя, у которого может быть доступ и к closed —
    см. /coaches/{coach_id}/sessions/for-me.
    """
    query = db.query(TrainingSession).filter(
        TrainingSession.coach_id == coach_id,
        TrainingSession.visibility == SessionVisibility.open,
        TrainingSession.datetime_ >= datetime.now(timezone.utc),
    )

    total = query.count()
    rows = (
        query.order_by(TrainingSession.datetime_.asc()).offset(offset).limit(limit).all()
    )
    return TrainingSessionListOut(
        items=[_to_out(db, s) for s in rows], total=total, limit=limit, offset=offset
    )


@router.get("/coaches/{coach_id}/sessions/for-me", response_model=TrainingSessionListOut)
def coach_sessions_for_parent(
    coach_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    """
    То же самое, но для авторизованного родителя: помимо открытых видны закрытые
    тренировки, доступные его детям (ученик тренера и, если у тренировки выбраны
    группы, состоит в одной из них).
    """
    query = db.query(TrainingSession).filter(
        TrainingSession.coach_id == coach_id,
        TrainingSession.datetime_ >= datetime.now(timezone.utc),
        or_(
            TrainingSession.visibility == SessionVisibility.open,
            closed_session_open_to_parent(user.id),
        ),
    )

    total = query.count()
    rows = query.order_by(TrainingSession.datetime_.asc()).offset(offset).limit(limit).all()
    return TrainingSessionListOut(
        items=[_to_out(db, s) for s in rows], total=total, limit=limit, offset=offset
    )
