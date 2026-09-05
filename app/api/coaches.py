from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.database import get_db
from app.models.coach import Coach
from app.models.enums import ExerciseAgeGroup, Specialization, UserRole
from app.models.training_session import TrainingSession
from app.models.enums import SessionVisibility
from app.models.user import User
from app.schemas.coach import (
    CoachProfileIn,
    CoachProfileOut,
    CoachCardOut,
    CoachCatalogOut,
    TrainingSessionShortOut,
)

router = APIRouter(prefix="/coaches", tags=["coaches"])


def _build_profile_out(coach: Coach, user: User) -> CoachProfileOut:
    return CoachProfileOut(
        id=user.id,
        name=user.name,
        city=user.city,
        specializations=[s.value for s in coach.specializations],
        experience_years=coach.experience_years,
        about=coach.about,
        age_groups=[a.value for a in (coach.age_groups or [])],
        visible_in_search=coach.visible_in_search,
    )


@router.post("/me/profile", response_model=CoachProfileOut)
def upsert_my_profile(
    data: CoachProfileIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    coach = db.get(Coach, user.id)
    if coach is None:
        coach = Coach(id=user.id)
        db.add(coach)

    coach.specializations = [Specialization(s) for s in data.specializations]
    coach.experience_years = data.experience_years
    coach.about = data.about
    coach.age_groups = [ExerciseAgeGroup(a) for a in data.age_groups] or None
    coach.visible_in_search = data.visible_in_search
    db.commit()
    db.refresh(coach)

    return _build_profile_out(coach, user)


@router.get("/me/profile", response_model=CoachProfileOut)
def get_my_profile(
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    coach = db.get(Coach, user.id)
    if coach is None:
        raise HTTPException(status_code=404, detail="Профиль ещё не заполнен")
    return _build_profile_out(coach, user)


@router.get("/{coach_id}", response_model=CoachProfileOut)
def get_coach_profile(coach_id: int, db: Session = Depends(get_db)):
    """Публичный просмотр профиля тренера — доступен без авторизации."""
    coach = db.get(Coach, coach_id)
    if coach is None:
        raise HTTPException(status_code=404, detail="Тренер не найден")
    user = db.get(User, coach_id)
    return _build_profile_out(coach, user)


@router.get("", response_model=CoachCatalogOut)
def catalog(
    city: str = Query(..., description="Город — обязательный фильтр"),
    specialization: Optional[str] = Query(
        default=None, description="Тренер найдётся, если эта специализация есть среди его"
    ),
    age_group: Optional[str] = Query(
        default=None, description="Например '10-12' — тренер найдётся, если ведёт эту группу"
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Coach, User)
        .join(User, User.id == Coach.id)
        .filter(User.role == UserRole.coach, User.city == city, Coach.visible_in_search.is_(True))
    )

    if specialization:
        query = query.filter(Coach.specializations.any(Specialization(specialization)))
    if age_group:
        query = query.filter(Coach.age_groups.any(ExerciseAgeGroup(age_group)))

    total = query.count()
    rows = query.order_by(User.id).offset(offset).limit(limit).all()

    now = datetime.now(timezone.utc)
    items: list[CoachCardOut] = []
    for coach, user in rows:
        # Ближайшие открытые тренировки — до 3 штук.
        # На масштабе Этапа 1 (немного тренеров в каталоге) N+1-запрос
        # приемлем; при росте каталога стоит перевести на один batched-запрос.
        upcoming = (
            db.query(TrainingSession)
            .filter(
                TrainingSession.coach_id == coach.id,
                TrainingSession.visibility == SessionVisibility.open,
                TrainingSession.datetime_ >= now,
            )
            .order_by(TrainingSession.datetime_.asc())
            .limit(3)
            .all()
        )
        items.append(
            CoachCardOut(
                id=user.id,
                name=user.name,
                specializations=[s.value for s in coach.specializations],
                experience_years=coach.experience_years,
                next_open_sessions=[
                    TrainingSessionShortOut(
                        id=s.id,
                        type=s.type.value,
                        datetime=s.datetime_,
                        max_players=s.max_players,
                        price=float(s.price) if s.price is not None else None,
                    )
                    for s in upcoming
                ],
            )
        )

    return CoachCatalogOut(items=items, total=total, limit=limit, offset=offset)
