"""
NocoDB Backup - Scheduler Module

Provides scheduled backup execution using APScheduler.
"""

from datetime import datetime
from typing import Callable

from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import Settings
from ui.console import backup_logger, console


def _log_next_run(event, scheduler: BlockingScheduler) -> None:
    """Log the next scheduled run time after job execution."""
    job = scheduler.get_job("nocodb_backup")
    if job and job.next_run_time:
        console.print(f"[dim]Next scheduled backup: {job.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}[/]")


def setup_scheduler(
    settings: Settings,
    backup_func: Callable[[], bool],
) -> BlockingScheduler:
    """Setup and configure the backup scheduler.

    Args:
        settings: Application settings.
        backup_func: Function to call for backup execution.

    Returns:
        Configured scheduler (not started).
    """
    scheduler = BlockingScheduler(timezone=settings.tz)

    if settings.backup_schedule_mode == "cron":
        # Cron mode: run at specific time
        trigger = CronTrigger(
            hour=settings.backup_schedule_hour,
            minute=settings.backup_schedule_minute,
            day_of_week=settings.backup_schedule_day_of_week,
            timezone=settings.tz,
        )

        # Format schedule description
        if settings.backup_schedule_day_of_week == "*":
            schedule_desc = f"daily at {settings.backup_schedule_hour:02d}:{settings.backup_schedule_minute:02d}"
        else:
            days_map = {
                "0": "Mon", "1": "Tue", "2": "Wed", "3": "Thu",
                "4": "Fri", "5": "Sat", "6": "Sun",
            }
            days = settings.backup_schedule_day_of_week.split(",")
            day_names = [days_map.get(d.strip(), d) for d in days]
            schedule_desc = f"on {', '.join(day_names)} at {settings.backup_schedule_hour:02d}:{settings.backup_schedule_minute:02d}"

        next_run_time = None  # Cron: wait for scheduled time

    else:
        # Interval mode: run every n hours, starting immediately
        trigger = IntervalTrigger(
            hours=settings.backup_schedule_interval_hours,
            timezone=settings.tz,
        )
        schedule_desc = f"every {settings.backup_schedule_interval_hours} hour(s)"
        next_run_time = datetime.now()  # Interval: run immediately at startup

    # Add the backup job
    scheduler.add_job(
        backup_func,
        trigger=trigger,
        id="nocodb_backup",
        name="NocoDB Backup Job",
        next_run_time=next_run_time,
        misfire_grace_time=3600,  # Allow 1 hour grace time for missed jobs
        coalesce=True,  # Combine missed runs into one
    )

    backup_logger.info(f"Scheduler configured: {schedule_desc} ({settings.tz})")

    return scheduler


def run_scheduler(scheduler: BlockingScheduler) -> None:
    """Run the scheduler (blocking).

    Args:
        scheduler: Configured scheduler.
    """
    # Register listener to show next run time after each execution
    scheduler.add_listener(
        lambda event: _log_next_run(event, scheduler),
        EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
    )

    console.print("[bold]Scheduler started. Press Ctrl+C to stop.[/]")
    console.print()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        backup_logger.info("Scheduler stopped by user")
        scheduler.shutdown(wait=False)
