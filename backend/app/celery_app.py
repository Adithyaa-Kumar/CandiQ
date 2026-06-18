"""
celery_app.py
─────────────
Celery application instance shared by the API (to enqueue tasks) and
the worker process (to execute them). Broker and result backend are
both Redis — simple, fast, sufficient at this scale.
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "candiq",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.ingest_task",
        "app.tasks.evaluate_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=60 * 60 * 24,  # 24h
    task_time_limit=60 * 30,       # hard kill at 30 min — evaluate_task should never run this long
    task_soft_time_limit=60 * 25,
)
