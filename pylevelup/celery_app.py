from celery import Celery
from celery.schedules import crontab

from pylevelup.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "pylevelup",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=["pylevelup.tasks.reminders", "pylevelup.tasks.ranking"],
)

celery_app.conf.update(
    task_default_queue="pylevelup",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "daily_reminders": {
        "task": "pylevelup.tasks.reminders.send_daily_reminders",
        "schedule": crontab(minute=0, hour=str(_settings.daily_reminder_hour_utc)),
    },
    "refresh_ranking": {
        "task": "pylevelup.tasks.ranking.refresh_ranking",
        "schedule": crontab(minute=f"*/{_settings.ranking_refresh_minutes}"),
    },
}
