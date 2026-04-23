from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Date
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base

class Habit(Base):
    __tablename__ = "habits"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class HabitLog(Base):
    __tablename__ = "habit_logs"
    id = Column(Integer, primary_key=True, index=True)
    habit_id = Column(Integer, ForeignKey("habits.id"), nullable=False)
    user_id = Column(Integer, index=True, nullable=False)
    date = Column(Date, nullable=False)
    is_done = Column(Boolean, default=False)
    note = Column(String, nullable=True)

class Metric(Base):
    __tablename__ = "metrics"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    date = Column(Date, nullable=False)
    metric_type = Column(String, nullable=False) # e.g. "weight", "sleep"
    value = Column(Float, nullable=False)
