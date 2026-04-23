import os
import redis
import json

REDIS_URI = os.getenv("REDIS_URI", "redis://localhost:6379/0")

try:
    redis_client = redis.from_url(REDIS_URI)
except Exception:
    redis_client = None

def notify_missed_habit(user_id: int, habit_name: str, date: str):
    if redis_client:
        message = {
            "user_id": user_id,
            "habit_name": habit_name,
            "date": date
        }
        redis_client.lpush("missed_habits_queue", json.dumps(message))
