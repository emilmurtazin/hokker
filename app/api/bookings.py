from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.booking import Booking
from app.models.coach_player import CoachPlayer
from app.models.enums import BookingStatus, CoachPlayerStatus
from app.models.player import Player
from app.models.training_session import TrainingSession
from app.models.user import User
from app.schemas.booking import BookingIn, BookingOut, ManualBookingIn
from app.services.notifications import notify

router = APIRouter(tags=["bookings"])

WAITLIST_INVITE_TTL_MINUTES = 15


def _confirmed_count(db: Session, session_id: int) -> int:
    return (
        db.query(func.count(Booking.id))
        .filter(Booking.session_id == session_id, Booking.status == BookingStatus.confirmed)
        .scalar()
    )


def _get_owned_child(db: Session, parent: User, child_id: int) -> Player:
    child = db.get(Player, child_id)
    if child is None or child.parent_id != parent.id:
        raise HTTPException(status_code=404, detail="Ребёнок не найден")
    return child


def _session_title(session: TrainingSession) -> str:
    return f"{session.type.value} {session.datetime_.strftime('%d.%m в %H:%M')}"


def _age(birth_date) -> int:
    today = datetime.now(timezone.utc).date()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def _to_booking_out(db: Session, booking: Booking) -> BookingOut:
    player = db.get(Player, booking.player_id)
    parent = db.get(User, player.parent_id) if player else None
    return BookingOut(
        id=booking.id,
        session_id=booking.session_id,
        player_id=booking.player_id,
        player_name=player.name if player else booking.manual_player_name,
        player_age=_age(player.birth_date) if player else None,
        player_position=player.position.value if player else None,
        parent_name=parent.name if parent else None,
        parent_phone=parent.phone if parent else None,
        status=booking.status.value,
        invited_at=booking.invited_at,
        created_at=booking.created_at,
    )


def _promote_next_waiting(db: Session, session_id: int) -> None:
    """
    Освободилось место — приглашаем первого из очереди (FIFO по created_at).
    TODO(Celery): Celery Beat должен через WAITLIST_INVITE_TTL_MINUTES проверять
    невостребованные invited -> expired и звать следующего. Пока это делается
    синхронно при следующем обращении к /bookings/{id}/confirm-invite (см.
    проверку истечения там) — рабочий, но не полностью автоматический вариант
    до появления Celery.
    """
    next_in_line = (
        db.query(Booking)
        .filter(Booking.session_id == session_id, Booking.status == BookingStatus.waiting)
        .order_by(Booking.created_at.asc())
        .first()
    )
    if next_in_line:
        next_in_line.status = BookingStatus.invited
        next_in_line.invited_at = datetime.now(timezone.utc)
        db.commit()

        session = db.get(TrainingSession, session_id)
        child = db.get(Player, next_in_line.player_id)
        parent = db.get(User, child.parent_id)
        notify(
            "waitlist_slot_available",
            parent,
            session_title=_session_title(session),
        )


@router.get("/sessions/{session_id}/bookings", response_model=list[BookingOut])
def session_bookings(
    session_id: int,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    """Все записи на конкретную тренировку — тренеру для управления заявками."""
    session = db.get(TrainingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    if session.coach_id != user.id:
        raise HTTPException(status_code=403, detail="Доступно только владельцу тренировки")

    rows = (
        db.query(Booking)
        .filter(Booking.session_id == session_id)
        .order_by(Booking.created_at.asc())
        .all()
    )
    return [_to_booking_out(db, b) for b in rows]


@router.post("/sessions/{session_id}/bookings", response_model=BookingOut)
def create_booking(
    session_id: int,
    data: BookingIn,
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    session = db.get(TrainingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    if session.datetime_ < datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="Тренировка уже прошла — запись недоступна")

    child = _get_owned_child(db, user, data.child_id)

    # Правило видимости: на closed-тренировку можно записаться только если
    # ребёнок уже активен в базе тренера.
    coach_player = (
        db.query(CoachPlayer)
        .filter(CoachPlayer.coach_id == session.coach_id, CoachPlayer.player_id == child.id)
        .first()
    )
    is_active_client = coach_player is not None and coach_player.status == CoachPlayerStatus.active

    if session.visibility.value == "closed" and not is_active_client:
        raise HTTPException(
            status_code=403, detail="Закрытая тренировка недоступна — ребёнок не в базе тренера"
        )

    existing = (
        db.query(Booking)
        .filter(Booking.session_id == session_id, Booking.player_id == child.id)
        .first()
    )
    if existing is not None and existing.status in (
        BookingStatus.pending,
        BookingStatus.confirmed,
        BookingStatus.waiting,
        BookingStatus.invited,
    ):
        raise HTTPException(status_code=409, detail="Ребёнок уже записан на эту тренировку")

    # Определяем статус новой записи:
    if not is_active_client:
        # Новый клиент — нужно подтверждение тренера, вне очереди по местам.
        new_status = BookingStatus.pending
    else:
        confirmed = _confirmed_count(db, session_id)
        new_status = (
            BookingStatus.confirmed if confirmed < session.max_players else BookingStatus.waiting
        )

    if existing is not None:
        # Переиспользуем строку (unique constraint на session_id+player_id)
        existing.status = new_status
        existing.invited_at = None
        booking = existing
    else:
        booking = Booking(session_id=session_id, player_id=child.id, status=new_status)
        db.add(booking)

    db.commit()
    db.refresh(booking)

    coach = db.get(User, session.coach_id)
    if new_status == BookingStatus.pending:
        notify("new_booking_request", coach, session_title=_session_title(session))
    elif new_status == BookingStatus.confirmed:
        notify("new_booking", coach, session_title=_session_title(session))

    return _to_booking_out(db, booking)


@router.post("/sessions/{session_id}/manual-bookings", response_model=BookingOut)
def create_manual_booking(
    session_id: int,
    data: ManualBookingIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    """Тренер добавляет ученика без учётной записи в приложении."""
    session = db.get(TrainingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    if session.coach_id != user.id:
        raise HTTPException(status_code=403, detail="Доступно только владельцу тренировки")
    if session.datetime_ < datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="Тренировка уже прошла")
    if _confirmed_count(db, session_id) >= session.max_players:
        raise HTTPException(status_code=409, detail="На тренировке больше нет свободных мест")

    player_name = data.player_name.strip()
    if not player_name:
        raise HTTPException(status_code=422, detail="Укажите имя ученика")

    existing = (
        db.query(Booking)
        .filter(
            Booking.session_id == session_id,
            Booking.player_id.is_(None),
            func.lower(Booking.manual_player_name) == player_name.lower(),
            Booking.status == BookingStatus.confirmed,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Ученик с таким именем уже добавлен")

    booking = Booking(
        session_id=session_id,
        player_id=None,
        manual_player_name=player_name,
        status=BookingStatus.confirmed,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return _to_booking_out(db, booking)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(
    booking_id: int,
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    child = db.get(Player, booking.player_id)
    if child is None or child.parent_id != user.id:
        raise HTTPException(status_code=403, detail="Можно отменять только записи своего ребёнка")

    was_confirmed = booking.status == BookingStatus.confirmed
    booking.status = BookingStatus.cancelled
    db.commit()

    session = db.get(TrainingSession, booking.session_id)
    coach = db.get(User, session.coach_id)
    notify("booking_cancelled", coach, session_title=_session_title(session))

    if was_confirmed:
        _promote_next_waiting(db, booking.session_id)

    db.refresh(booking)
    return _to_booking_out(db, booking)


@router.post("/bookings/{booking_id}/confirm-invite", response_model=BookingOut)
def confirm_invite(
    booking_id: int,
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    """Родитель подтверждает место, освободившееся в листе ожидания."""
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    child = db.get(Player, booking.player_id)
    if child is None or child.parent_id != user.id:
        raise HTTPException(status_code=403, detail="Доступно только для своего ребёнка")

    if booking.status != BookingStatus.invited:
        raise HTTPException(status_code=409, detail="Запись не находится в статусе приглашения")

    deadline = booking.invited_at + timedelta(minutes=WAITLIST_INVITE_TTL_MINUTES)
    if datetime.now(timezone.utc) > deadline:
        booking.status = BookingStatus.expired
        db.commit()
        _promote_next_waiting(db, booking.session_id)
        raise HTTPException(status_code=410, detail="Время на подтверждение истекло")

    booking.status = BookingStatus.confirmed
    db.commit()
    db.refresh(booking)
    return _to_booking_out(db, booking)


@router.post("/bookings/{booking_id}/approve", response_model=BookingOut)
def approve_booking(
    booking_id: int,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    """Тренер подтверждает заявку от нового клиента (booking.status=pending)."""
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    session = db.get(TrainingSession, booking.session_id)
    if session.coach_id != user.id:
        raise HTTPException(status_code=403, detail="Доступно только владельцу тренировки")

    if booking.status != BookingStatus.pending:
        raise HTTPException(status_code=409, detail="Запись не ожидает подтверждения")

    confirmed = _confirmed_count(db, session.id)
    booking.status = (
        BookingStatus.confirmed if confirmed < session.max_players else BookingStatus.waiting
    )

    coach_player = (
        db.query(CoachPlayer)
        .filter(CoachPlayer.coach_id == session.coach_id, CoachPlayer.player_id == booking.player_id)
        .first()
    )
    if coach_player is None:
        db.add(
            CoachPlayer(
                coach_id=session.coach_id,
                player_id=booking.player_id,
                status=CoachPlayerStatus.active,
            )
        )
    elif coach_player.status != CoachPlayerStatus.active:
        coach_player.status = CoachPlayerStatus.active

    db.commit()
    db.refresh(booking)

    child = db.get(Player, booking.player_id)
    parent = db.get(User, child.parent_id)
    notify("booking_approved", parent, session_title=_session_title(session))

    return _to_booking_out(db, booking)


@router.post("/bookings/{booking_id}/reject", response_model=BookingOut)
def reject_booking(
    booking_id: int,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    session = db.get(TrainingSession, booking.session_id)
    if session.coach_id != user.id:
        raise HTTPException(status_code=403, detail="Доступно только владельцу тренировки")

    if booking.status != BookingStatus.pending:
        raise HTTPException(status_code=409, detail="Запись не ожидает подтверждения")

    booking.status = BookingStatus.rejected
    db.commit()
    db.refresh(booking)

    child = db.get(Player, booking.player_id)
    parent = db.get(User, child.parent_id)
    notify("booking_rejected", parent, session_title=_session_title(session))

    return _to_booking_out(db, booking)


@router.get("/coaches/me/bookings", response_model=list[BookingOut])
def my_pending_bookings(
    status_filter: Optional[str] = Query(default="pending", alias="status"),
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Booking)
        .join(TrainingSession, TrainingSession.id == Booking.session_id)
        .filter(TrainingSession.coach_id == user.id)
    )
    if status_filter:
        query = query.filter(Booking.status == BookingStatus(status_filter))

    rows = query.order_by(Booking.created_at.asc()).all()
    return [_to_booking_out(db, b) for b in rows]


@router.get("/children/{child_id}/bookings", response_model=list[BookingOut])
def child_bookings(
    child_id: int,
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    _get_owned_child(db, user, child_id)
    rows = (
        db.query(Booking)
        .filter(Booking.player_id == child_id)
        .order_by(Booking.created_at.desc())
        .all()
    )
    return [_to_booking_out(db, b) for b in rows]
