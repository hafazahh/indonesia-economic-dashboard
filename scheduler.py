"""Auto-update scheduler using APScheduler (PRD §9).

APScheduler BackgroundScheduler runs in a daemon thread inside the Flask
process, so the dashboard keeps serving while data refreshes every 6 hours.
"""
import sys
import os

from apscheduler.schedulers.background import BackgroundScheduler

sys.path.insert(0, os.path.dirname(__file__))
from data_fetcher import fetch_all

UPDATE_INTERVAL_HOURS = 6

_scheduler = None


def _job():
    """Refresh all indicators from the World Bank API."""
    try:
        print("[Scheduler] Fetching data...")
        fetch_all()
        print("[Scheduler] Fetch complete")
    except Exception as exc:  # keep the scheduler alive on any fetch failure
        print(f"[Scheduler] Error: {exc}")


def start_scheduler():
    """Start the APScheduler background scheduler (idempotent)."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _job,
        trigger="interval",
        hours=UPDATE_INTERVAL_HOURS,
        id="fetch_world_bank",
        replace_existing=True,
    )
    _scheduler.start()
    print(f"[Scheduler] APScheduler started, interval={UPDATE_INTERVAL_HOURS}h")
    return _scheduler


def stop_scheduler():
    """Shut the scheduler down cleanly."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] APScheduler stopped")
    _scheduler = None
