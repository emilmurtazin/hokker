"""
Группы клиентов тренера: создать группу, переименовать, состав, удалить —
и назначить группы конкретному ученику.

Зачем группы: закрытую тренировку можно сделать доступной не всем ученикам тренера,
а только выбранным группам, и записывать на тренировку сразу целыми группами
(см. app/services/access.py, POST /sessions/{id}/participants).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.coach_players import _build_out
from app.api.deps import require_role
from app.core.database import get_db
from app.models.client_group import ClientGroup, ClientGroupMember, SessionGroup
from app.models.coach_player import CoachPlayer
from app.models.enums import CoachPlayerStatus
from app.models.training_session import TrainingSession
from app.models.user import User
from app.schemas.client_group import (
    ClientGroupIn,
    ClientGroupOut,
    GroupMembersIn,
    PlayerGroupsIn,
)
from app.schemas.coach_player import CoachPlayerOut
from app.services.access import validated_group_ids

router = APIRouter(tags=["client_groups"])


def _own_group(db: Session, coach: User, group_id: int) -> ClientGroup:
    group = db.get(ClientGroup, group_id)
    if group is None or group.coach_id != coach.id:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    return group


def _upcoming_sessions_count(db: Session, group_id: int) -> int:
    return (
        db.query(func.count(SessionGroup.session_id))
        .join(TrainingSession, TrainingSession.id == SessionGroup.session_id)
        .filter(SessionGroup.group_id == group_id, TrainingSession.datetime_ >= datetime.now(timezone.utc))
        .scalar()
    )


def _to_out(db: Session, group: ClientGroup) -> ClientGroupOut:
    # В составе считаем только активных учеников: убранных из базы тренер уже не видит.
    member_ids = [
        cp_id
        for (cp_id,) in db.query(ClientGroupMember.coach_player_id)
        .join(CoachPlayer, CoachPlayer.id == ClientGroupMember.coach_player_id)
        .filter(ClientGroupMember.group_id == group.id, CoachPlayer.status == CoachPlayerStatus.active)
        .order_by(ClientGroupMember.coach_player_id)
        .all()
    ]
    return ClientGroupOut(
        id=group.id,
        name=group.name,
        members_count=len(member_ids),
        member_ids=member_ids,
        upcoming_sessions_count=_upcoming_sessions_count(db, group.id),
    )


def _ensure_name_free(db: Session, coach: User, name: str, except_id: int | None = None) -> None:
    query = db.query(ClientGroup.id).filter(
        ClientGroup.coach_id == coach.id, func.lower(ClientGroup.name) == name.lower()
    )
    if except_id is not None:
        query = query.filter(ClientGroup.id != except_id)
    if query.first() is not None:
        raise HTTPException(status_code=409, detail="Группа с таким названием уже есть")


@router.get("/coaches/me/groups", response_model=list[ClientGroupOut])
def list_groups(user: User = Depends(require_role("coach")), db: Session = Depends(get_db)):
    groups = db.query(ClientGroup).filter(ClientGroup.coach_id == user.id).order_by(ClientGroup.name).all()
    return [_to_out(db, g) for g in groups]


@router.post("/coaches/me/groups", response_model=ClientGroupOut, status_code=201)
def create_group(
    data: ClientGroupIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    _ensure_name_free(db, user, data.name)
    group = ClientGroup(coach_id=user.id, name=data.name)
    db.add(group)
    try:
        db.commit()
    except IntegrityError:  # гонка двух одинаковых запросов
        db.rollback()
        raise HTTPException(status_code=409, detail="Группа с таким названием уже есть") from None
    db.refresh(group)
    return _to_out(db, group)


@router.patch("/coaches/me/groups/{group_id}", response_model=ClientGroupOut)
def rename_group(
    group_id: int,
    data: ClientGroupIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    group = _own_group(db, user, group_id)
    _ensure_name_free(db, user, data.name, except_id=group.id)
    group.name = data.name
    db.commit()
    return _to_out(db, group)


@router.delete("/coaches/me/groups/{group_id}", status_code=204)
def delete_group(
    group_id: int,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    group = _own_group(db, user, group_id)
    upcoming = _upcoming_sessions_count(db, group.id)
    if upcoming:
        # Иначе закрытая тренировка, выбранная только для этой группы, молча стала бы
        # доступна ВСЕМ ученикам тренера.
        raise HTTPException(
            status_code=409,
            detail=f"Группа выбрана в предстоящих тренировках ({upcoming}). "
            "Сначала измените доступ в этих тренировках или отмените их.",
        )
    db.delete(group)  # состав и прошедшие тренировки удаляет БД (ON DELETE CASCADE)
    db.commit()
    return None


@router.put("/coaches/me/groups/{group_id}/members", response_model=ClientGroupOut)
def set_group_members(
    group_id: int,
    data: GroupMembersIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    """Задаёт состав группы целиком (список id учеников из GET /coaches/me/players)."""
    group = _own_group(db, user, group_id)
    ids = list(dict.fromkeys(data.coach_player_ids))
    if ids:
        valid = {
            cp_id
            for (cp_id,) in db.query(CoachPlayer.id).filter(
                CoachPlayer.coach_id == user.id,
                CoachPlayer.status == CoachPlayerStatus.active,
                CoachPlayer.id.in_(ids),
            )
        }
        if valid != set(ids):
            raise HTTPException(status_code=422, detail="Один из учеников не найден в вашей базе")
    db.query(ClientGroupMember).filter(ClientGroupMember.group_id == group.id).delete()
    db.add_all(ClientGroupMember(group_id=group.id, coach_player_id=cp_id) for cp_id in ids)
    db.commit()
    return _to_out(db, group)


@router.put("/coaches/me/players/{coach_player_id}/groups", response_model=CoachPlayerOut)
def set_player_groups(
    coach_player_id: int,
    data: PlayerGroupsIn,
    user: User = Depends(require_role("coach")),
    db: Session = Depends(get_db),
):
    """Задаёт группы ученика целиком (ученик может состоять в нескольких группах)."""
    cp = db.get(CoachPlayer, coach_player_id)
    if cp is None or cp.coach_id != user.id:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    group_ids = validated_group_ids(db, user.id, data.group_ids)
    db.query(ClientGroupMember).filter(ClientGroupMember.coach_player_id == cp.id).delete()
    db.add_all(ClientGroupMember(group_id=g, coach_player_id=cp.id) for g in group_ids)
    db.commit()
    return _build_out(db, cp)
