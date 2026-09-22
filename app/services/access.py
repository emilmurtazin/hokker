"""
Кто видит и на что может записаться: закрытые тренировки и группы клиентов.

Правило для закрытой тренировки: ребёнок допущен, если он «активный ученик» тренера
(coach_players.status = active) и
  * у тренировки не выбрано ни одной группы — тренировка для всех учеников тренера
    (так работали закрытые тренировки до появления групп);
  * иначе — ребёнок состоит хотя бы в одной из выбранных групп.
Открытые тренировки доступны всем; группы для них не действуют.

Родитель видит закрытую тренировку, если допущен хотя бы один его ребёнок.
"""

from fastapi import HTTPException
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.client_group import ClientGroup, ClientGroupMember, SessionGroup
from app.models.coach_player import CoachPlayer
from app.models.enums import CoachPlayerStatus, SessionVisibility
from app.models.player import Player
from app.models.training_session import TrainingSession
from app.models.user import User


def closed_session_open_to_parent(parent_id: int):
    """
    SQL-условие для запросов по TrainingSession: «закрытая тренировка доступна хотя бы
    одному ребёнку этого родителя». Используется в ленте и в списке тренера.
    """
    # ВАЖНО: correlate() обязателен. Без него SQLAlchemy добавляет training_sessions в FROM
    # вложенного подзапроса ещё раз (получается не связанное с внешним запросом
    # «FROM session_groups, training_sessions»), и «у тренировки нет групп» становится
    # ложным, как только группы есть хотя бы у какой-нибудь другой тренировки.
    session_has_groups = (
        exists().where(SessionGroup.session_id == TrainingSession.id).correlate(TrainingSession)
    )
    child_in_session_group = (
        exists()
        .where(
            SessionGroup.session_id == TrainingSession.id,
            ClientGroupMember.group_id == SessionGroup.group_id,
            ClientGroupMember.coach_player_id == CoachPlayer.id,
        )
        .correlate(TrainingSession, CoachPlayer)
    )
    eligible_client = (
        exists()
        .where(
            CoachPlayer.coach_id == TrainingSession.coach_id,
            CoachPlayer.status == CoachPlayerStatus.active,
            CoachPlayer.player_id.in_(select(Player.id).where(Player.parent_id == parent_id)),
            or_(~session_has_groups, child_in_session_group),
        )
        .correlate(TrainingSession)
    )
    return and_(TrainingSession.visibility == SessionVisibility.closed, eligible_client)


def child_access(db: Session, session: TrainingSession, child_id: int) -> str:
    """
    'ok' — можно записывать; 'not_client' — ребёнка нет в базе тренера;
    'not_in_group' — в базе есть, но не в группе этой тренировки.
    """
    if session.visibility == SessionVisibility.open:
        return "ok"
    link = (
        db.query(CoachPlayer)
        .filter(CoachPlayer.coach_id == session.coach_id, CoachPlayer.player_id == child_id)
        .first()
    )
    if link is None or link.status != CoachPlayerStatus.active:
        return "not_client"
    group_ids = session_group_ids(db, session.id)
    if not group_ids:
        return "ok"
    in_group = (
        db.query(ClientGroupMember)
        .filter(
            ClientGroupMember.coach_player_id == link.id,
            ClientGroupMember.group_id.in_(group_ids),
        )
        .first()
    )
    return "ok" if in_group is not None else "not_in_group"


def parent_can_view_session(db: Session, session: TrainingSession, user: User | None) -> bool:
    """Просмотр тренировки: открытую видят все, закрытую — тренер, допущенные родители и те, кто уже записан."""
    if session.visibility == SessionVisibility.open:
        return True
    if user is None:
        return False
    if user.id == session.coach_id:
        return True
    if user.role.value != "parent":
        return False
    already_booked = (
        db.query(Booking.id)
        .join(Player, Player.id == Booking.player_id)
        .filter(Booking.session_id == session.id, Player.parent_id == user.id)
        .first()
    )
    if already_booked is not None:
        return True  # у родителя есть запись — расписание не должно ломаться после смены групп
    return (
        db.query(TrainingSession.id)
        .filter(TrainingSession.id == session.id, closed_session_open_to_parent(user.id))
        .first()
        is not None
    )


def session_group_ids(db: Session, session_id: int) -> list[int]:
    return [g for (g,) in db.query(SessionGroup.group_id).filter(SessionGroup.session_id == session_id).all()]


def session_groups(db: Session, session_id: int) -> list[ClientGroup]:
    return (
        db.query(ClientGroup)
        .join(SessionGroup, SessionGroup.group_id == ClientGroup.id)
        .filter(SessionGroup.session_id == session_id)
        .order_by(ClientGroup.name)
        .all()
    )


def validated_group_ids(db: Session, coach_id: int, group_ids: list[int] | None) -> list[int]:
    """Группы должны существовать и принадлежать этому тренеру (чужие — 422). Дубликаты убираем."""
    ids = list(dict.fromkeys(group_ids or []))
    if not ids:
        return []
    found = {
        g
        for (g,) in db.query(ClientGroup.id)
        .filter(ClientGroup.coach_id == coach_id, ClientGroup.id.in_(ids))
        .all()
    }
    if len(found) != len(ids):
        raise HTTPException(status_code=422, detail="Одна из выбранных групп не найдена")
    return ids
