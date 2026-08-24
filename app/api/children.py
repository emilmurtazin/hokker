from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.enums import Position
from app.models.player import Player
from app.models.user import User
from app.schemas.player import ChildIn, ChildOut, ChildUpdate

router = APIRouter(tags=["children"])


@router.post("/parents/me/children", response_model=ChildOut)
def add_child(
    data: ChildIn,
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    child = Player(
        name=data.name,
        birth_date=data.birth_date,
        position=Position(data.position),
        parent_id=user.id,
    )
    db.add(child)
    db.commit()
    db.refresh(child)
    return child


@router.get("/parents/me/children", response_model=List[ChildOut])
def list_my_children(
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    return db.query(Player).filter(Player.parent_id == user.id).order_by(Player.id).all()


def _get_own_child_or_404(child_id: int, user: User, db: Session) -> Player:
    child = db.get(Player, child_id)
    if child is None or child.parent_id != user.id:
        raise HTTPException(status_code=404, detail="Ребёнок не найден")
    return child


@router.patch("/children/{child_id}", response_model=ChildOut)
def update_child(
    child_id: int,
    data: ChildUpdate,
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    child = _get_own_child_or_404(child_id, user, db)

    updates = data.model_dump(exclude_unset=True)
    if "position" in updates:
        updates["position"] = Position(updates["position"])
    for field, value in updates.items():
        setattr(child, field, value)

    db.commit()
    db.refresh(child)
    return child


@router.delete("/children/{child_id}", status_code=204)
def delete_child(
    child_id: int,
    user: User = Depends(require_role("parent")),
    db: Session = Depends(get_db),
):
    child = _get_own_child_or_404(child_id, user, db)
    db.delete(child)
    db.commit()
