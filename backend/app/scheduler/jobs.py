"""Scheduler job functions.

One row per scheduled invocation — the functions own their DB session
and swallow exceptions at the boundary so APScheduler's worker thread
can never die from a pipeline error. The in-service code
(`run_pipeline_for_all_active_tenants`) already handles per-tenant and
per-source failures; this wrapper is the last safety net."""
from __future__ import annotations

import time

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.pipeline_service import run_pipeline_for_all_active_tenants

logger = get_logger(__name__)


def run_pipeline_for_all_tenants() -> None:
    """Scheduled tick: run the pipeline for every active tenant.

    Never raises — any unexpected error is logged and swallowed so the
    scheduler keeps firing the next tick."""
    started = time.monotonic()
    logger.info("Scheduled pipeline tick started")
    try:
        with SessionLocal() as db:
            summaries = run_pipeline_for_all_active_tenants(db)
    except Exception:
        logger.exception("Scheduled pipeline tick crashed")
        return

    elapsed = time.monotonic() - started
    logger.info(
        "Scheduled pipeline tick finished tenants=%d total_collected=%d "
        "total_signals=%d total_item_errors=%d elapsed_sec=%.2f",
        len(summaries),
        sum(s.collected_item_count for s in summaries),
        sum(s.inserted_signal_count for s in summaries),
        sum(s.failed_item_count for s in summaries),
        elapsed,
    )
