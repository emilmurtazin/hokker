from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.database import get_db
from app.models.booking import Booking
from app.models.coach_player import CoachPlayer
from app.models.enums import BookingStatus, CoachPlayerStatus, SessionType, SessionVisibility
from app.models.player import Player
from app.models.training_session import TrainingSession
from app.models.user import User
from app.schemas.training_session import (
    TrainingSessionIn,
    TrainingSessionOut,
    TrainingSessionListOut,
)
from app.services.notifications import notify

router = APIRouter(tags=["sessions"])


def _booked_count(db: Session, session_id: int) -> int:
    """Сколько мест реально занято (только confirmed — waiting/invited в лимит не входят)."""
    return (
        db.query(func.count(Booking.id))
        .filter(Booking.session_id == session_id, Booking.status == BookingStatus.confirmed)
        .scalar()
    )


def _session_title(s: TrainingSession) -> str:
    return f"{s.type.value} {s.datetime_.strftime('%d.%m в %H:%M')}"


def _to_out(db: Session, s: TrainingSession) -> TrainingSessionOut:
    return TrainingSessionOut(
        id=s.id,
        coach_id=s.coach_id,
        type=s.type.value,
        visibility=s.visibility.value,
        datetime=s.datetime_,
        arena_name=s.arena_name,
        max_players=s.max_players,
        booked_count=_booked_count(db, s.id),
    )


@router.post("/sessions", response_model=TrainingSessionOut)
def create_session(
    data: TrainingSessionIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    session = TrainingSession(
        coach_id=user.id,
        type=SessionType(data.type),
        visibility=SessionVisibility(data.visibility),
        datetime_=data.datetime,
        arena_name=data.arena_name,
        max_players=data.max_players,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _to_out(db, session)


@router.get("/sessions/{session_id}", response_model=TrainingSessionOut)
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = db.get(TrainingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    return _to_out(db, session)


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

    session.type = SessionType(data.type)
    session.visibility = SessionVisibility(data.visibility)
    session.datetime_ = data.datetime
    session.arena_name = data.arena_name
    session.max_players = data.max_players
    db.commit()
    db.refresh(session)
    return _to_out(db, session)


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
    # до удаления, пока ещё видим их bookings.
    affected = (
        db.query(Booking)
        .filter(
            Booking.session_id == session_id,
            Booking.status.in_(
                [
                    BookingStatus.confirmed,
                    BookingStatus.waiting,
                    BookingStatus.invited,
                    BookingStatus.pending,
                ]
            ),
        )
        .all()
    )
    title = _session_title(session)
    for b in affected:
        child = db.get(Player, b.player_id)
        parent = db.get(User, child.parent_id)
        notify("session_cancelled", parent, session_title=title)

    db.delete(session)  # bookings удалятся каскадно (ondelete=CASCADE)
    db.commit()
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
        items=[_to_out(db, s) for s in rows], total=total, limit=limit, offset=offset
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
    То же самое, но для авторизованного родителя: если у него есть ребёнок
    с активной связью с этим тренером — видны и closed-тренировки тоже.
    """
    has_active_child = (
        db.query(CoachPlayer)
        .join(Player, Player.id == CoachPlayer.player_id)
        .filter(
            CoachPlayer.coach_id == coach_id,
            CoachPlayer.status == CoachPlayerStatus.active,
            Player.parent_id == user.id,
        )
        .first()
        is not None
    )

    query = db.query(TrainingSession).filter(TrainingSession.coach_id == coach_id)
    if not has_active_child:
        query = query.filter(TrainingSession.visibility == SessionVisibility.open)

    total = query.count()
    rows = query.order_by(TrainingSession.datetime_.asc()).offset(offset).limit(limit).all()
    return TrainingSessionListOut(
        items=[_to_out(db, s) for s in rows], total=total, limit=limit, offset=offset
    )
