from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import date
from app import models, schemas, database
from app.auth_middleware import get_current_user
from app.redis_client import notify_missed_habit

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Habit Service")

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/habits", response_model=schemas.HabitResponse)
def create_habit(habit: schemas.HabitCreate, db: Session = Depends(database.get_db), user_id: int = Depends(get_current_user)):
    new_habit = models.Habit(user_id=user_id, name=habit.name, description=habit.description)
    db.add(new_habit)
    db.commit()
    db.refresh(new_habit)
    return new_habit

@app.get("/habits", response_model=list[schemas.HabitResponse])
def get_habits(db: Session = Depends(database.get_db), user_id: int = Depends(get_current_user)):
    return db.query(models.Habit).filter(models.Habit.user_id == user_id).all()

@app.post("/habits/{habit_id}/logs/{log_date}", response_model=schemas.HabitLogResponse)
def log_habit(habit_id: int, log_date: date, log: schemas.HabitLogCreateUpdate, db: Session = Depends(database.get_db), user_id: int = Depends(get_current_user)):
    habit = db.query(models.Habit).filter(models.Habit.id == habit_id, models.Habit.user_id == user_id).first()
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    existing_log = db.query(models.HabitLog).filter(models.HabitLog.habit_id == habit_id, models.HabitLog.date == log_date).first()
    
    if existing_log:
        existing_log.is_done = log.is_done
        if log.note is not None:
            existing_log.note = log.note
        db.commit()
        db.refresh(existing_log)
        
        # If it was marked not done and previously done, or just marked not done, notify optionally
        if not existing_log.is_done:
            notify_missed_habit(user_id, habit.name, str(log_date))
            
        return existing_log
    else:
        new_log = models.HabitLog(habit_id=habit_id, user_id=user_id, date=log_date, is_done=log.is_done, note=log.note)
        db.add(new_log)
        db.commit()
        db.refresh(new_log)
        
        if not new_log.is_done:
            notify_missed_habit(user_id, habit.name, str(log_date))

        return new_log

@app.get("/habits/logs", response_model=list[schemas.HabitLogResponse])
def get_all_logs(db: Session = Depends(database.get_db), user_id: int = Depends(get_current_user)):
    return db.query(models.HabitLog).filter(models.HabitLog.user_id == user_id).all()

@app.post("/metrics/{log_date}", response_model=schemas.MetricResponse)
def log_metric(log_date: date, metric: schemas.MetricCreate, db: Session = Depends(database.get_db), user_id: int = Depends(get_current_user)):
    existing_metric = db.query(models.Metric).filter(
        models.Metric.user_id == user_id, 
        models.Metric.date == log_date,
        models.Metric.metric_type == metric.metric_type
    ).first()
    
    if existing_metric:
        existing_metric.value = metric.value
        db.commit()
        db.refresh(existing_metric)
        return existing_metric
    else:
        new_metric = models.Metric(user_id=user_id, date=log_date, metric_type=metric.metric_type, value=metric.value)
        db.add(new_metric)
        db.commit()
        db.refresh(new_metric)
        return new_metric

@app.get("/metrics", response_model=list[schemas.MetricResponse])
def get_metrics(metric_type: str = None, db: Session = Depends(database.get_db), user_id: int = Depends(get_current_user)):
    query = db.query(models.Metric).filter(models.Metric.user_id == user_id)
    if metric_type:
        query = query.filter(models.Metric.metric_type == metric_type)
    return query.all()
