from celery import Celery

from app.config import settings

celery_app = Celery("scheduler", broker=settings.celery_redis_url, backend=settings.celery_redis_url)
celery_app.conf.timezone = "UTC"
celery_app.conf.beat_schedule = {
    "scan-due-scheduled-posts": {
        "task": "app.tasks.scan_due_scheduled_posts",
        "schedule": settings.beat_scan_interval_seconds,
    }
}

# Import so the task is registered with this Celery app when the worker
# or beat process starts (`celery -A app.celery_app worker/beat`).
from app import tasks  # noqa: E402,F401
