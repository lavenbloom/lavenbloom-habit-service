from pydantic import BaseModel
from datetime import date, datetime

class HabitCreate(BaseModel):
    name: str
    description: str | None = None

class HabitResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: str | None = None
    created_at: datetime
    class Config:
        from_attributes = True

class HabitLogCreateUpdate(BaseModel):
    is_done: bool
    note: str | None = None

class HabitLogResponse(BaseModel):
    id: int
    habit_id: int
    user_id: int
    date: date
    is_done: bool
    note: str | None = None
    class Config:
        from_attributes = True

class MetricCreate(BaseModel):
    metric_type: str
    value: float

class MetricResponse(BaseModel):
    id: int
    user_id: int
    date: date
    metric_type: str
    value: float
    class Config:
        from_attributes = True
