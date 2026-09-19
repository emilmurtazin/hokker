from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.attendance import Attendance
from app.models.booking import Booking
from app.models.enums import AttendanceStatus, BookingStatus
from app.models.player import Player
from app.models.training_session import TrainingSession
from app.models.user import User
from app.schemas.attendance import AttendanceBulkIn, AttendanceOut

router = APIRouter(tags=["attendance"])


@router.get("/sessions/{session_id}/attendance", response_model=List[AttendanceOut])
def get_session_attendance(
    session_id: int,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    session = db.get(TrainingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    if session.coach_id != user.id:
        raise HTTPException(status_code=403, detail="Доступно только владельцу тренировки")

    # Список записанных — только confirmed (те, кто реально придёт).
    bookings = (
        db.query(Booking)
        .filter(
            Booking.session_id == session_id,
            Booking.status == BookingStatus.confirmed,
            Booking.player_id.is_not(None),
        )
        .all()
    )
    existing_marks = {
        a.player_id: a
        for a in db.query(Attendance).filter(Attendance.session_id == session_id).all()
    }

    result = []
    for b in bookings:
        player = db.get(Player, b.player_id)
        mark = existing_marks.get(b.player_id)
        result.append(
            AttendanceOut(
                player_id=player.id,
                player_name=player.name,
                status=mark.status.value if mark else None,
                updated_at=mark.updated_at if mark else None,
            )
        )
    return result


@router.post("/sessions/{session_id}/attendance", response_model=List[AttendanceOut])
def mark_attendance(
    session_id: int,
    data: AttendanceBulkIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    """
    Отметить посещаемость сразу для нескольких детей. Можно вызывать повторно
    в любой момент (в том числе позже, «отметить позже» из ТЗ) — статус просто
    перезаписывается (upsert по session_id+player_id).
    """
    session = db.get(TrainingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    if session.coach_id != user.id:
        raise HTTPException(status_code=403, detail="Доступно только владельцу тренировки")

    for mark in data.marks:
        # Проверяем, что ребёнок реально был записан на эту тренировку —
        # нельзя отметить посещаемость постороннему.
        booking = (
            db.query(Booking)
            .filter(Booking.session_id == session_id, Booking.player_id == mark.player_id)
            .first()
        )
        if booking is None:
            raise HTTPException(
                status_code=404, detail=f"Ребёнок {mark.player_id} не записан на эту тренировку"
            )

        existing = (
            db.query(Attendance)
            .filter(Attendance.session_id == session_id, Attendance.player_id == mark.player_id)
            .first()
        )
        if existing:
            existing.status = AttendanceStatus(mark.status)
        else:
            db.add(
                Attendance(
                    session_id=session_id,
                    player_id=mark.player_id,
                    status=AttendanceStatus(mark.status),
                )
            )
    db.commit()

    return get_session_attendance(session_id, user, db)


@router.get("/children/{child_id}/attendance", response_model=List[AttendanceOut])
def child_attendance_history(
    child_id: int,
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    child = db.get(Player, child_id)
    if child is None or child.parent_id != user.id:
        raise HTTPException(status_code=404, detail="Ребёнок не найден")

    marks = (
        db.query(Attendance)
        .filter(Attendance.player_id == child_id)
        .order_by(Attendance.created_at.desc())
        .all()
    )
    return [
        AttendanceOut(
            player_id=child.id,
            player_name=child.name,
            status=m.status.value,
            updated_at=m.updated_at,
        )
        for m in marks
    ]
