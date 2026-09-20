from collections import defaultdict
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.attendance import Attendance
from app.models.booking import Booking
from app.models.enums import AttendanceStatus, BookingStatus, SkillCategory
from app.models.player import Player
from app.models.rating import Rating
from app.models.training_session import TrainingSession
from app.models.user import User
from app.schemas.rating import (
    GroupRatingIn,
    PlayerPassportOut,
    ProgressOut,
    ProgressPointOut,
    RatingOut,
    RatingsBulkIn,
    SkillAverageOut,
)
from app.services.formatting import session_title as _session_title
from app.services.notifications import notify

router = APIRouter(tags=["ratings"])

ALL_SKILLS = [s.value for s in SkillCategory]


def _get_session_owned_by(db: Session, session_id: int, coach: User) -> TrainingSession:
    session = db.get(TrainingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    if session.coach_id != coach.id:
        raise HTTPException(status_code=403, detail="Доступно только владельцу тренировки")
    return session


def _confirmed_player_ids(db: Session, session_id: int) -> set[int]:
    rows = (
        db.query(Booking.player_id)
        .filter(
            Booking.session_id == session_id,
            Booking.status == BookingStatus.confirmed,
            Booking.player_id.is_not(None),
        )
        .all()
    )
    return {r[0] for r in rows}


def _upsert_rating(db: Session, session_id: int, player_id: int, skill: str, score: int, comment: str | None):
    existing = (
        db.query(Rating)
        .filter(
            Rating.session_id == session_id,
            Rating.player_id == player_id,
            Rating.skill == SkillCategory(skill),
        )
        .first()
    )
    if existing:
        existing.score = score
        existing.comment = comment
    else:
        db.add(
            Rating(
                session_id=session_id,
                player_id=player_id,
                skill=SkillCategory(skill),
                score=score,
                comment=comment,
            )
        )


def _notify_affected_parents(db: Session, session: TrainingSession, player_ids: set[int]) -> None:
    title = _session_title(session)
    for player_id in player_ids:
        player = db.get(Player, player_id)
        if player is None:
            continue
        parent = db.get(User, player.parent_id)
        notify(
            "rating_added",
            parent,
            session_title=title,
            path=f"/children/{player.id}/progress",
        )


@router.post("/sessions/{session_id}/ratings/group", response_model=List[RatingOut])
def rate_group(
    session_id: int,
    data: GroupRatingIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    """Одна оценка сразу всем, кто confirmed записан на тренировку («поставить всей группе сразу»)."""
    session = _get_session_owned_by(db, session_id, user)
    player_ids = _confirmed_player_ids(db, session_id)
    if not player_ids:
        raise HTTPException(status_code=409, detail="На тренировке нет подтверждённых участников")

    for player_id in player_ids:
        _upsert_rating(db, session_id, player_id, data.skill, data.score, data.comment)
    db.commit()

    _notify_affected_parents(db, session, player_ids)
    return get_session_ratings(session_id, user, db)


@router.post("/sessions/{session_id}/ratings", response_model=List[RatingOut])
def rate_individually(
    session_id: int,
    data: RatingsBulkIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    """
    Индивидуальные оценки — как для первичной простановки по каждому
    отдельно, так и для корректировки после rate_group.
    """
    session = _get_session_owned_by(db, session_id, user)
    confirmed_ids = _confirmed_player_ids(db, session_id)

    touched_player_ids = set()
    for entry in data.entries:
        if entry.player_id not in confirmed_ids:
            raise HTTPException(
                status_code=404,
                detail=f"Ребёнок {entry.player_id} не записан (confirmed) на эту тренировку",
            )
        _upsert_rating(db, session_id, entry.player_id, entry.skill, entry.score, entry.comment)
        touched_player_ids.add(entry.player_id)
    db.commit()

    _notify_affected_parents(db, session, touched_player_ids)
    return get_session_ratings(session_id, user, db)


@router.get("/sessions/{session_id}/ratings", response_model=List[RatingOut])
def get_session_ratings(
    session_id: int,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    _get_session_owned_by(db, session_id, user)
    rows = db.query(Rating).filter(Rating.session_id == session_id).all()
    out = []
    for r in rows:
        player = db.get(Player, r.player_id)
        out.append(
            RatingOut(
                player_id=r.player_id,
                player_name=player.name,
                skill=r.skill.value,
                score=r.score,
                comment=r.comment,
                updated_at=r.updated_at,
            )
        )
    return out


@router.get("/children/{child_id}/ratings", response_model=List[RatingOut])
def child_ratings(
    child_id: int,
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    child = db.get(Player, child_id)
    if child is None or child.parent_id != user.id:
        raise HTTPException(status_code=404, detail="Ребёнок не найден")

    rows = (
        db.query(Rating)
        .filter(Rating.player_id == child_id)
        .order_by(Rating.updated_at.desc())
        .all()
    )
    return [
        RatingOut(
            player_id=child.id,
            player_name=child.name,
            skill=r.skill.value,
            score=r.score,
            comment=r.comment,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


def _compute_progress(db: Session, child_id: int) -> ProgressOut:
    rows = (
        db.query(Rating, TrainingSession.datetime_)
        .join(TrainingSession, TrainingSession.id == Rating.session_id)
        .filter(Rating.player_id == child_id)
        .all()
    )

    radar_scores: dict[str, list[int]] = defaultdict(list)
    weekly_scores: dict[tuple[str, str], list[int]] = defaultdict(list)
    monthly_scores: dict[tuple[str, str], list[int]] = defaultdict(list)

    for rating, dt in rows:
        skill = rating.skill.value
        radar_scores[skill].append(rating.score)

        iso_year, iso_week, _ = dt.isocalendar()
        week_label = f"{iso_year}-W{iso_week:02d}"
        weekly_scores[(week_label, skill)].append(rating.score)

        month_label = f"{dt.year}-{dt.month:02d}"
        monthly_scores[(month_label, skill)].append(rating.score)

    radar = [
        SkillAverageOut(skill=skill, average=round(sum(scores) / len(scores), 2), count=len(scores))
        for skill, scores in radar_scores.items()
    ]
    weekly = [
        ProgressPointOut(period=period, skill=skill, average=round(sum(scores) / len(scores), 2))
        for (period, skill), scores in sorted(weekly_scores.items())
    ]
    monthly = [
        ProgressPointOut(period=period, skill=skill, average=round(sum(scores) / len(scores), 2))
        for (period, skill), scores in sorted(monthly_scores.items())
    ]

    return ProgressOut(radar=radar, weekly=weekly, monthly=monthly)


@router.get("/children/{child_id}/progress", response_model=ProgressOut)
def child_progress(
    child_id: int,
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    child = db.get(Player, child_id)
    if child is None or child.parent_id != user.id:
        raise HTTPException(status_code=404, detail="Ребёнок не найден")
    return _compute_progress(db, child_id)


def _age(birth_date: date) -> int:
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


@router.get("/children/{child_id}/passport", response_model=PlayerPassportOut)
def child_passport(
    child_id: int,
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    """«Паспорт хоккеиста» — общая сводка по всем тренерам, у кого занимался ребёнок."""
    child = db.get(Player, child_id)
    if child is None or child.parent_id != user.id:
        raise HTTPException(status_code=404, detail="Ребёнок не найден")

    progress = _compute_progress(db, child_id)

    all_ratings = db.query(Rating.score).filter(Rating.player_id == child_id).all()
    scores = [r[0] for r in all_ratings]
    overall_average = round(sum(scores) / len(scores), 2) if scores else None

    total_sessions = (
        db.query(Booking)
        .filter(Booking.player_id == child_id, Booking.status == BookingStatus.confirmed)
        .count()
    )
    attendance_total = db.query(Attendance).filter(Attendance.player_id == child_id).count()
    attendance_present = (
        db.query(Attendance)
        .filter(Attendance.player_id == child_id, Attendance.status == AttendanceStatus.present)
        .count()
    )

    return PlayerPassportOut(
        player_id=child.id,
        name=child.name,
        age=_age(child.birth_date),
        position=child.position.value,
        overall_average=overall_average,
        radar=progress.radar,
        total_sessions=total_sessions,
        attendance_present=attendance_present,
        attendance_total=attendance_total,
    )
