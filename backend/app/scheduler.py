"""APScheduler: her gun 08:30 (Europe/Istanbul) senkronu baslatir.

Not: reCAPTCHA nedeniyle tam otomatik degil. Zamanlanan is tarayiciyi acar ve
kullanicidan captcha cozmesini bekler (captcha_wait_timeout_s); cozulmezse
'skipped_no_captcha' olarak loglanir.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings
from . import sync_manager

_scheduler: BackgroundScheduler | None = None


def _scheduled_job():
    if sync_manager.is_running():
        return
    sync_manager.start_sync(resume=True)


def start_scheduler():
    global _scheduler
    if not settings.scheduler_enabled or _scheduler:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone=settings.timezone)
    _scheduler.add_job(
        _scheduled_job,
        CronTrigger(hour=settings.sync_hour, minute=settings.sync_minute,
                    timezone=settings.timezone),
        id="daily_sync", replace_existing=True, misfire_grace_time=3600,
    )
    _scheduler.start()
    return _scheduler


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
