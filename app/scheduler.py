"""
Scheduler — runs Prophet forecasts every night at 2:00 AM UTC.
Uses APScheduler with AsyncIOScheduler.
"""
from __future__ import annotations

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.forecasting import run_forecasts_for_all_bins

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler():
    """Call this once on app startup."""
    scheduler.add_job(
        _run_nightly_forecasts,
        trigger=CronTrigger(hour=2, minute=0, timezone="UTC"),
        id="nightly_forecasts",
        replace_existing=True,
        misfire_grace_time=3600,  # run even if missed by up to 1hr
    )
    scheduler.start()
    logger.info("✅ Scheduler started — nightly forecasts at 02:00 UTC")


async def _run_nightly_forecasts():
    logger.info("🌙 Nightly forecast job starting...")
    try:
        result = await run_forecasts_for_all_bins()
        logger.info(
            "✅ Nightly forecasts done — %d/%d bins passed MAPE spec",
            result.get("passed_mape", 0),
            result.get("total_bins", 0),
        )
    except Exception as exc:
        logger.error("❌ Nightly forecast job failed: %s", exc)