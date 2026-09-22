from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.attendance import Attendance
from app.models.booking import Booking
from app.models.client_group import ClientGroupMember
from app.models.coach_player import CoachPlayer
from app.models.enums import AttendanceStatus, BookingStatus, CoachPlayerStatus
from app.models.player import Player
from app.models.training_session import TrainingSession
from app.models.user import User
from app.schemas.coach_player import (
    AttendanceHistoryEntryOut,
    AttendanceSummary,
    CoachPlayerInviteIn,
    CoachPlayerOut,
    MessageIn,
    ParentLookupChildOut,
    ParentLookupOut,
)
from app.services.notifications import notify
from app.services.telegram import esc, send_message_or_http_error

router = APIRouter(tags=["coach_players"])


def _age(birth_date: date) -> int:
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def _build_out(db: Session, cp: CoachPlayer) -> CoachPlayerOut:
    player = db.get(Player, cp.player_id)
    parent = db.get(User, player.parent_id)
    coach = db.get(User, cp.coach_id)

    attendance_rows = (
        db.query(Attendance.status, func.count(Attendance.id))
        .join(TrainingSession, TrainingSession.id == Attendance.session_id)
        .filter(TrainingSession.coach_id == cp.coach_id, Attendance.player_id == cp.player_id)
        .group_by(Attendance.status)
        .all()
    )
    counts = {status.value: 0 for status in AttendanceStatus}
    for status, count in attendance_rows:
        counts[status.value] = count

    sessions_count = (
        db.query(func.count(Booking.id))
        .join(TrainingSession, TrainingSession.id == Booking.session_id)
        .filter(
            TrainingSession.coach_id == cp.coach_id,
            Booking.player_id == cp.player_id,
            Booking.status == BookingStatus.confirmed,
        )
        .scalar()
    )

    return CoachPlayerOut(
        id=cp.id,
        coach_id=cp.coach_id,
        coach_name=coach.name,
        player_id=player.id,
        player_name=player.name,
        birth_date=player.birth_date,
        age=_age(player.birth_date),
        position=player.position.value,
        status=cp.status.value,
        parent_id=parent.id,
        parent_name=parent.name,
        parent_phone=parent.phone,
        attendance=AttendanceSummary(**counts),
        sessions_count=sessions_count,
        created_at=cp.created_at,
        group_ids=[
            g
            for (g,) in db.query(ClientGroupMember.group_id)
            .filter(ClientGroupMember.coach_player_id == cp.id)
            .order_by(ClientGroupMember.group_id)
            .all()
        ],
    )


@router.get("/coaches/lookup-parent", response_model=ParentLookupOut)
def lookup_parent_by_phone(
    phone: str = Query(...),
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    """
    Поиск родителя и его детей по номеру телефона — чтобы вручную добавить
    существующего клиента в базу, не зная его id заранее.
    """
    parent = db.query(User).filter(User.phone == phone, User.role == "parent").first()
    if parent is None:
        raise HTTPException(
            status_code=404, detail="Родитель с таким телефоном не зарегистрирован в системе"
        )
    children = db.query(Player).filter(Player.parent_id == parent.id).all()
    return ParentLookupOut(
        parent_id=parent.id,
        parent_name=parent.name,
        parent_phone=parent.phone,
        children=[
            ParentLookupChildOut(
                id=c.id, name=c.name, birth_date=c.birth_date, position=c.position.value
            )
            for c in children
        ],
    )


@router.post("/coaches/me/players", response_model=CoachPlayerOut)
def invite_player(
    data: CoachPlayerInviteIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    """Тренер вручную добавляет существующего (найденного через lookup-parent) ребёнка."""
    child = db.get(Player, data.child_id)
    if child is None:
        raise HTTPException(status_code=404, detail="Ребёнок не найден")

    existing = (
        db.query(CoachPlayer)
        .filter(CoachPlayer.coach_id == user.id, CoachPlayer.player_id == child.id)
        .first()
    )
    if existing is not None and existing.status != CoachPlayerStatus.removed:
        raise HTTPException(status_code=409, detail="Ребёнок уже в базе (или ожидает подтверждения)")

    if existing is not None:
        existing.status = CoachPlayerStatus.pending
        cp = existing
    else:
        cp = CoachPlayer(coach_id=user.id, player_id=child.id, status=CoachPlayerStatus.pending)
        db.add(cp)

    db.commit()
    db.refresh(cp)

    parent = db.get(User, child.parent_id)
    notify("coach_invite", parent, coach_name=user.name)

    return _build_out(db, cp)


@router.get("/coaches/me/players", response_model=list[CoachPlayerOut])
def list_my_players(
    status_filter: str | None = Query(default="active", alias="status"),
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    query = db.query(CoachPlayer).filter(CoachPlayer.coach_id == user.id)
    if status_filter:
        query = query.filter(CoachPlayer.status == CoachPlayerStatus(status_filter))
    rows = query.order_by(CoachPlayer.created_at.desc()).all()
    return [_build_out(db, cp) for cp in rows]


@router.get("/coaches/me/players/{coach_player_id}", response_model=CoachPlayerOut)
def get_my_player(
    coach_player_id: int,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    cp = db.get(CoachPlayer, coach_player_id)
    if cp is None or cp.coach_id != user.id:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return _build_out(db, cp)


@router.get(
    "/coaches/me/players/{coach_player_id}/attendance",
    response_model=list[AttendanceHistoryEntryOut],
)
def get_player_attendance_history(
    coach_player_id: int,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    """
    История посещений конкретного ребёнка на тренировках ЭТОГО тренера —
    все тренировки, куда он был confirmed-записан, с отметкой посещаемости
    (или без неё, если ещё не отмечена).
    """
    cp = db.get(CoachPlayer, coach_player_id)
    if cp is None or cp.coach_id != user.id:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    bookings = (
        db.query(Booking)
        .join(TrainingSession, TrainingSession.id == Booking.session_id)
        .filter(
            TrainingSession.coach_id == cp.coach_id,
            Booking.player_id == cp.player_id,
            Booking.status == BookingStatus.confirmed,
        )
        .all()
    )

    attendance_by_session = {
        a.session_id: a.status.value
        for a in db.query(Attendance).filter(Attendance.player_id == cp.player_id).all()
    }

    entries = []
    for b in bookings:
        session = db.get(TrainingSession, b.session_id)
        entries.append(
            AttendanceHistoryEntryOut(
                session_id=session.id,
                session_type=session.type.value,
                session_datetime=session.datetime_,
                status=attendance_by_session.get(session.id),
            )
        )
    entries.sort(key=lambda e: e.session_datetime, reverse=True)
    return entries


@router.delete("/coaches/me/players/{coach_player_id}", status_code=204)
def remove_player(
    coach_player_id: int,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    cp = db.get(CoachPlayer, coach_player_id)
    if cp is None or cp.coach_id != user.id:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    cp.status = CoachPlayerStatus.removed
    db.commit()
    return None


@router.post("/coaches/me/players/{coach_player_id}/message", status_code=204)
def message_parent(
    coach_player_id: int,
    data: MessageIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    cp = db.get(CoachPlayer, coach_player_id)
    if cp is None or cp.coach_id != user.id:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    player = db.get(Player, cp.player_id)
    parent = db.get(User, player.parent_id)
    if not parent.telegram_chat_id:
        raise HTTPException(status_code=409, detail="У родителя не привязан Telegram")

    send_message_or_http_error(
        parent.telegram_chat_id,
        f"✉️ Сообщение от тренера {esc(user.name)}:\n\n{esc(data.text)}",
    )
    return None


# --- Со стороны родителя: просмотр и подтверждение приглашений ---


@router.get("/parents/me/invites", response_model=list[CoachPlayerOut])
def my_invites(
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(CoachPlayer)
        .join(Player, Player.id == CoachPlayer.player_id)
        .filter(Player.parent_id == user.id, CoachPlayer.status == CoachPlayerStatus.pending)
        .all()
    )
    return [_build_out(db, cp) for cp in rows]


@router.post("/parents/me/invites/{coach_player_id}/accept", response_model=CoachPlayerOut)
def accept_invite(
    coach_player_id: int,
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    cp = db.get(CoachPlayer, coach_player_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    player = db.get(Player, cp.player_id)
    if player.parent_id != user.id:
        raise HTTPException(status_code=403, detail="Доступно только для своего ребёнка")
    if cp.status != CoachPlayerStatus.pending:
        raise HTTPException(status_code=409, detail="Приглашение не ожидает подтверждения")

    cp.status = CoachPlayerStatus.active
    db.commit()
    db.refresh(cp)
    return _build_out(db, cp)


@router.post("/parents/me/invites/{coach_player_id}/decline", status_code=204)
def decline_invite(
    coach_player_id: int,
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    cp = db.get(CoachPlayer, coach_player_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    player = db.get(Player, cp.player_id)
    if player.parent_id != user.id:
        raise HTTPException(status_code=403, detail="Доступно только для своего ребёнка")
    if cp.status != CoachPlayerStatus.pending:
        raise HTTPException(status_code=409, detail="Приглашение не ожидает подтверждения")

    cp.status = CoachPlayerStatus.removed
    db.commit()
    return None
