from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.database import get_db
from app.models.coach_player import CoachPlayer
from app.models.enums import CoachPlayerStatus, ExerciseAgeGroup, ExerciseCategory, ExerciseLevel
from app.models.exercise import Exercise
from app.models.player import Player
from app.models.user import User
from app.schemas.exercise import ExerciseIn, ExerciseListOut, ExerciseOut, SendExerciseIn
from app.services.telegram import send_message

router = APIRouter(tags=["exercises"])


def _to_out(e: Exercise) -> ExerciseOut:
    return ExerciseOut(
        id=e.id,
        title=e.title,
        category=e.category.value,
        age_group=e.age_group.value,
        level=e.level.value,
        video_url=e.video_url,
        description=e.description,
        repetitions=e.repetitions,
        key_points=e.key_points,
        created_at=e.created_at,
    )


# --- Публичный каталог (любой авторизованный пользователь) ---


@router.get("/exercises", response_model=ExerciseListOut)
def list_exercises(
    category: Optional[str] = Query(default=None),
    age_group: Optional[str] = Query(default=None),
    level: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Exercise)
    if category:
        query = query.filter(Exercise.category == ExerciseCategory(category))
    if age_group:
        query = query.filter(Exercise.age_group == ExerciseAgeGroup(age_group))
    if level:
        query = query.filter(Exercise.level == ExerciseLevel(level))

    total = query.count()
    rows = query.order_by(Exercise.created_at.desc()).offset(offset).limit(limit).all()
    return ExerciseListOut(
        items=[_to_out(e) for e in rows], total=total, limit=limit, offset=offset
    )


@router.get("/exercises/{exercise_id}", response_model=ExerciseOut)
def get_exercise(
    exercise_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Упражнение не найдено")
    return _to_out(exercise)


# --- Тренер отправляет упражнение родителю («отработать дома») ---


@router.post("/exercises/{exercise_id}/send", status_code=204)
def send_exercise(
    exercise_id: int,
    data: SendExerciseIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Упражнение не найдено")

    cp = (
        db.query(CoachPlayer)
        .filter(
            CoachPlayer.coach_id == user.id,
            CoachPlayer.player_id == data.child_id,
            CoachPlayer.status == CoachPlayerStatus.active,
        )
        .first()
    )
    if cp is None:
        raise HTTPException(
            status_code=403, detail="Можно отправлять упражнения только своим активным клиентам"
        )

    child = db.get(Player, data.child_id)
    parent = db.get(User, child.parent_id)
    if not parent.telegram_chat_id:
        raise HTTPException(status_code=409, detail="У родителя не привязан Telegram")

    text = f"🏒 Тренер {user.name} рекомендует отработать дома:\n\n" f"<b>{exercise.title}</b>\n{exercise.video_url}"
    if exercise.repetitions:
        text += f"\n\nПовторения: {exercise.repetitions}"
    if exercise.key_points:
        text += f"\nКлючевые точки: {exercise.key_points}"
    if data.note:
        text += f"\n\nКомментарий тренера: {data.note}"

    send_message(parent.telegram_chat_id, text)
    return None


# --- Админка (только роль admin) ---


@router.post("/admin/exercises", response_model=ExerciseOut)
def create_exercise(
    data: ExerciseIn,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    exercise = Exercise(
        title=data.title,
        category=ExerciseCategory(data.category),
        age_group=ExerciseAgeGroup(data.age_group),
        level=ExerciseLevel(data.level),
        video_url=data.video_url,
        description=data.description,
        repetitions=data.repetitions,
        key_points=data.key_points,
    )
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return _to_out(exercise)


@router.patch("/admin/exercises/{exercise_id}", response_model=ExerciseOut)
def update_exercise(
    exercise_id: int,
    data: ExerciseIn,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Упражнение не найдено")

    exercise.title = data.title
    exercise.category = ExerciseCategory(data.category)
    exercise.age_group = ExerciseAgeGroup(data.age_group)
    exercise.level = ExerciseLevel(data.level)
    exercise.video_url = data.video_url
    exercise.description = data.description
    exercise.repetitions = data.repetitions
    exercise.key_points = data.key_points
    db.commit()
    db.refresh(exercise)
    return _to_out(exercise)


@router.delete("/admin/exercises/{exercise_id}", status_code=204)
def delete_exercise(
    exercise_id: int,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Упражнение не найдено")
    db.delete(exercise)
    db.commit()
    return None
