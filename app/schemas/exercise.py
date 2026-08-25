from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

EXERCISE_CATEGORY = Literal["skating", "stickhandling", "shooting", "strength", "goalie", "game"]
AGE_GROUP = Literal["6-9", "10-12", "13+"]
LEVEL = Literal["beginner", "intermediate", "advanced"]


class ExerciseIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    category: EXERCISE_CATEGORY
    age_group: AGE_GROUP
    level: LEVEL
    video_url: str = Field(..., max_length=1000)
    description: Optional[str] = None
    repetitions: Optional[str] = Field(default=None, max_length=255)
    key_points: Optional[str] = None


class ExerciseOut(BaseModel):
    id: int
    title: str
    category: EXERCISE_CATEGORY
    age_group: AGE_GROUP
    level: LEVEL
    video_url: str
    description: Optional[str] = None
    repetitions: Optional[str] = None
    key_points: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExerciseListOut(BaseModel):
    items: List[ExerciseOut]
    total: int
    limit: int
    offset: int


class SendExerciseIn(BaseModel):
    child_id: int
    note: Optional[str] = Field(default=None, max_length=500)
