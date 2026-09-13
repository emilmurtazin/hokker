from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

EXERCISE_CATEGORY = Literal["skating", "stickhandling", "shooting", "strength", "goalie", "game"]
EXERCISE_LOCATION = Literal["on_ice", "gym", "off_ice"]
AGE_GROUP = Literal["6-9", "10-12", "13+"]
CONTENT_STATUS = Literal["complete", "draft"]


class ExerciseIn(BaseModel):
    code: Optional[str] = Field(default=None, max_length=20)
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: EXERCISE_CATEGORY
    location: EXERCISE_LOCATION
    age_group: AGE_GROUP
    players_text: Optional[str] = Field(default=None, max_length=50)
    duration_text: Optional[str] = Field(default=None, max_length=50)
    equipment_text: Optional[str] = Field(default=None, max_length=255)
    needs_puck: Optional[bool] = None
    steps: Optional[List[str]] = None
    coach_tips: Optional[List[str]] = None
    simplify_tips: Optional[List[str]] = None
    complicate_tips: Optional[List[str]] = None
    hockey_connection: Optional[str] = None
    qualities: Optional[List[str]] = None
    content_status: CONTENT_STATUS = "draft"
    video_url: Optional[str] = Field(default=None, max_length=1000)
    image_url: Optional[str] = Field(default=None, max_length=1000)


class ExerciseOut(BaseModel):
    id: int
    code: Optional[str] = None
    title: str
    description: Optional[str] = None
    category: EXERCISE_CATEGORY
    location: EXERCISE_LOCATION
    age_group: AGE_GROUP
    players_text: Optional[str] = None
    duration_text: Optional[str] = None
    equipment_text: Optional[str] = None
    needs_puck: Optional[bool] = None
    steps: Optional[List[str]] = None
    coach_tips: Optional[List[str]] = None
    simplify_tips: Optional[List[str]] = None
    complicate_tips: Optional[List[str]] = None
    hockey_connection: Optional[str] = None
    qualities: Optional[List[str]] = None
    content_status: CONTENT_STATUS
    video_url: Optional[str] = None
    image_url: Optional[str] = None
    created_at: datetime


class ExerciseListOut(BaseModel):
    items: List[ExerciseOut]
    total: int
    limit: int
    offset: int


class SendExerciseIn(BaseModel):
    child_id: int
    note: Optional[str] = Field(default=None, max_length=500)
