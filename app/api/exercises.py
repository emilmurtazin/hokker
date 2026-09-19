from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.database import get_db
from app.models.coach_player import CoachPlayer
from app.models.enums import (
    CoachPlayerStatus,
    ExerciseAgeGroup,
    ExerciseCategory,
    ExerciseContentStatus,
    ExerciseLocation,
)
from app.models.exercise import Exercise
from app.models.player import Player
from app.models.user import User
from app.schemas.exercise import ExerciseIn, ExerciseListOut, ExerciseOut, SendExerciseIn
from app.services.telegram import esc, send_message_or_http_error

router = APIRouter(tags=["exercises"])


def _to_out(e: Exercise) -> ExerciseOut:
    return ExerciseOut(
        id=e.id,
        code=e.code,
        title=e.title,
        description=e.description,
        category=e.category.value,
        location=e.location.value,
        age_group=e.age_group.value,
        players_text=e.players_text,
        duration_text=e.duration_text,
        equipment_text=e.equipment_text,
        needs_puck=e.needs_puck,
        steps=e.steps,
        coach_tips=e.coach_tips,
        simplify_tips=e.simplify_tips,
        complicate_tips=e.complicate_tips,
        hockey_connection=e.hockey_connection,
        qualities=e.qualities,
        content_status=e.content_status.value,
        video_url=e.video_url,
        image_url=e.image_url,
        created_at=e.created_at,
    )


# --- Публичный каталог (любой авторизованный пользователь) ---


@router.get("/exercises", response_model=ExerciseListOut)
def list_exercises(
    category: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None, description="on_ice / gym / off_ice"),
    age_group: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Exercise)
    if category:
        query = query.filter(Exercise.category == ExerciseCategory(category))
    if location:
        query = query.filter(Exercise.location == ExerciseLocation(location))
    if age_group:
        query = query.filter(Exercise.age_group == ExerciseAgeGroup(age_group))

    total = query.count()
    # Сортируем по коду (ОФП-01, ОФП-02, ...) — так каталог выглядит
    # предсказуемо, как в исходных карточках, а не в случайном порядке.
    rows = query.order_by(Exercise.code.asc().nulls_last(), Exercise.id.asc()).offset(offset).limit(limit).all()
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
            status_code=403, detail="Можно отправлять упражнения только своим активным ученикам"
        )

    child = db.get(Player, data.child_id)
    parent = db.get(User, child.parent_id)
    if not parent.telegram_chat_id:
        raise HTTPException(status_code=409, detail="У родителя не привязан Telegram")

    text = f"🏒 Тренер {esc(user.name)} рекомендует отработать дома:\n\n<b>{esc(exercise.title)}</b>"
    if exercise.video_url:
        text += f"\n{esc(exercise.video_url)}"
    if exercise.description:
        text += f"\n\n{esc(exercise.description)}"
    if exercise.steps:
        text += "\n\nКак выполнять:\n" + "\n".join(
            f"{i+1}. {esc(s)}" for i, s in enumerate(exercise.steps)
        )
    if data.note:
        text += f"\n\nКомментарий тренера: {esc(data.note)}"

    send_message_or_http_error(parent.telegram_chat_id, text)
    return None


# --- Админка (только роль admin) ---


def _apply_fields(exercise: Exercise, data: ExerciseIn) -> None:
    exercise.code = data.code
    exercise.title = data.title
    exercise.description = data.description
    exercise.category = ExerciseCategory(data.category)
    exercise.location = ExerciseLocation(data.location)
    exercise.age_group = ExerciseAgeGroup(data.age_group)
    exercise.players_text = data.players_text
    exercise.duration_text = data.duration_text
    exercise.equipment_text = data.equipment_text
    exercise.needs_puck = data.needs_puck
    exercise.steps = data.steps
    exercise.coach_tips = data.coach_tips
    exercise.simplify_tips = data.simplify_tips
    exercise.complicate_tips = data.complicate_tips
    exercise.hockey_connection = data.hockey_connection
    exercise.qualities = data.qualities
    exercise.content_status = ExerciseContentStatus(data.content_status)
    exercise.video_url = data.video_url
    exercise.image_url = data.image_url


@router.post("/admin/exercises", response_model=ExerciseOut)
def create_exercise(
    data: ExerciseIn,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    exercise = Exercise()
    _apply_fields(exercise, data)
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
    _apply_fields(exercise, data)
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
