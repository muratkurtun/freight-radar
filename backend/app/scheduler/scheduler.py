"""In-process APScheduler.

Why APScheduler and not Celery / RQ / Redis?
    Budget-friendly MVP. One FastAPI worker, one sidecar thread, one
    Postgres; no extra broker or worker fleet. This is intentional — see
    the production notes at the bottom of this module for when to
    outgrow it.

Job model
    A single `pipeline_all_tenants` job fires on a fixed interval
    (60 min by default, configurable via `pipeline_interval_minutes`).
    `max_instances=1` + `coalesce=True` prevents overlap within a
    process: if a previous tick is still running when the next one is
    due, APScheduler skips the late fire instead of queueing it.

Lifecycle
    `start_scheduler()` is called from the FastAPI lifespan on app
    startup; `shutdown_scheduler()` from the shutdown side. Both are
    idempotent so `uvicorn --reload` re-imports don't spawn a second
    scheduler in the same process.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.core.logging import get_logger
from app.scheduler.jobs import run_pipeline_for_all_tenants

logger = get_logger(__name__)

PIPELINE_JOB_ID = "pipeline_all_tenants"

_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


def start_scheduler() -> None:
    """Start the in-process scheduler. Idempotent.

    No-ops when already running or when `scheduler_enabled=False` — the
    latter is useful for tests and for ad-hoc ops pods that shouldn't
    also be firing scheduled work."""
    global _scheduler
    settings = get_settings()

    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled by config (scheduler_enabled=False)")
        return

    with _lock:
        if _scheduler is not None and _scheduler.running:
            logger.debug("Scheduler already running; skipping start")
            return

        scheduler = BackgroundScheduler(
            timezone="UTC",
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
        )
        scheduler.add_job(
            run_pipeline_for_all_tenants,
            trigger=IntervalTrigger(minutes=settings.pipeline_interval_minutes),
            id=PIPELINE_JOB_ID,
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc),  # also fire once immediately on boot
        )
        scheduler.add_listener(_on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        scheduler.start()
        _scheduler = scheduler

        logger.info(
            "Scheduler started job=%s interval_minutes=%s",
            PIPELINE_JOB_ID,
            settings.pipeline_interval_minutes,
        )


def shutdown_scheduler() -> None:
    """Stop the scheduler without waiting for running jobs to finish.

    Idempotent. A `wait=True` stop would block process exit on a long
    LLM call; we accept losing the tail of an in-flight tick since the
    pipeline's work is already durable in `pipeline_runs` up to the
    last commit point."""
    global _scheduler
    with _lock:
        if _scheduler is None:
            return
        try:
            _scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")
        except Exception:
            logger.exception("Scheduler shutdown raised")
        finally:
            _scheduler = None


def _on_job_event(event: JobExecutionEvent) -> None:
    """Surface APScheduler job outcomes through our logger.

    APScheduler already logs internally, but routing via our configured
    logger gives us a single destination and a uniform format across
    app + scheduler output."""
    if event.exception is not None:
        logger.error(
            "Scheduled job crashed job=%s scheduled_run_time=%s error=%s",
            event.job_id,
            event.scheduled_run_time,
            event.exception,
            exc_info=(type(event.exception), event.exception, event.traceback),
        )
    else:
        logger.info(
            "Scheduled job completed job=%s scheduled_run_time=%s",
            event.job_id,
            event.scheduled_run_time,
        )
