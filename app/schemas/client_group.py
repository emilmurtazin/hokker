from typing import List

from pydantic import BaseModel, Field, field_validator


class ClientGroupIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Название группы не может быть пустым")
        return value


class ClientGroupOut(BaseModel):
    id: int
    name: str
    members_count: int
    # id связей coach_players (те же, что в GET /coaches/me/players → id) — состав группы
    member_ids: List[int]
    # Сколько будущих закрытых тренировок доступны этой группе (нужно для предупреждения при удалении)
    upcoming_sessions_count: int = 0


class GroupMembersIn(BaseModel):
    coach_player_ids: List[int]


class PlayerGroupsIn(BaseModel):
    group_ids: List[int]


class SessionGroupsIn(BaseModel):
    group_ids: List[int]
