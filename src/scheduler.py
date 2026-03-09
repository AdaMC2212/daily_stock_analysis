# -*- coding: utf-8 -*-
"""
Timezone-aware daily scheduler.
"""

import logging
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class GracefulShutdown:
    """Handle SIGINT/SIGTERM and stop the scheduler cleanly."""

    def __init__(self):
        self.shutdown_requested = False
        self._lock = threading.Lock()
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        _ = frame
        with self._lock:
            if not self.shutdown_requested:
                logger.info("Received shutdown signal (%s), waiting for current task to finish...", signum)
                self.shutdown_requested = True

    @property
    def should_shutdown(self) -> bool:
        with self._lock:
            return self.shutdown_requested


class Scheduler:
    """Run a task once per day at a configured local time."""

    def __init__(self, schedule_time: str = "08:00", timezone_name: str = "Asia/Kuala_Lumpur"):
        self._hour, self._minute = self._parse_schedule_time(schedule_time)
        self.schedule_time = schedule_time
        self.timezone = ZoneInfo(timezone_name)
        self.shutdown_handler = GracefulShutdown()
        self._task_callback: Optional[Callable] = None
        self._running = False
        self._last_run_date = None

    @staticmethod
    def _parse_schedule_time(schedule_time: str) -> tuple[int, int]:
        """Parse HH:MM schedule string."""
        try:
            hour_str, minute_str = schedule_time.split(":", 1)
            hour = int(hour_str)
            minute = int(minute_str)
        except Exception as exc:
            raise ValueError("schedule_time must use HH:MM format") from exc

        if hour not in range(24) or minute not in range(60):
            raise ValueError("schedule_time must use a valid 24-hour clock time")
        return hour, minute

    def _now(self) -> datetime:
        """Return current time in the configured scheduler timezone."""
        return datetime.now(timezone.utc).astimezone(self.timezone)

    def _next_run_datetime(self) -> Optional[datetime]:
        """Return the next scheduled runtime in the configured timezone."""
        if self._task_callback is None:
            return None

        now = self._now()
        candidate = now.replace(hour=self._hour, minute=self._minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    def _should_run_now(self, now: datetime) -> bool:
        """Return whether the current local date's scheduled slot is due."""
        if self._task_callback is None:
            return False

        current_date = now.date()
        if self._last_run_date == current_date:
            return False

        scheduled = now.replace(hour=self._hour, minute=self._minute, second=0, microsecond=0)
        return now >= scheduled

    def set_daily_task(self, task: Callable, run_immediately: bool = True):
        """Register the task to be run daily."""
        self._task_callback = task
        logger.info(
            "Configured daily scheduled task at %s (%s)",
            self.schedule_time,
            self.timezone.key,
        )

        if run_immediately:
            logger.info("Running scheduled task immediately once on startup...")
            self._safe_run_task()

    def _safe_run_task(self):
        """Run the task with logging and exception isolation."""
        if self._task_callback is None:
            return

        started_at = self._now()
        try:
            logger.info("=" * 50)
            logger.info(
                "Scheduled task started - %s (%s)",
                started_at.strftime("%Y-%m-%d %H:%M:%S"),
                self.timezone.key,
            )
            logger.info("=" * 50)

            self._task_callback()
            self._last_run_date = started_at.date()

            logger.info(
                "Scheduled task completed - %s (%s)",
                self._now().strftime("%Y-%m-%d %H:%M:%S"),
                self.timezone.key,
            )
        except Exception as exc:
            logger.exception("Scheduled task failed: %s", exc)

    def run(self):
        """Run the scheduler loop until interrupted."""
        self._running = True
        logger.info("Scheduler started.")
        logger.info("Next run: %s", self._get_next_run_time())

        while self._running and not self.shutdown_handler.should_shutdown:
            now = self._now()
            if self._should_run_now(now):
                self._safe_run_task()
            time.sleep(30)

            if now.minute == 0 and now.second < 30:
                logger.info("Scheduler heartbeat. Next run: %s", self._get_next_run_time())

        logger.info("Scheduler stopped.")

    def _get_next_run_time(self) -> str:
        """Return next run time as a string for logs."""
        next_run = self._next_run_datetime()
        if next_run is None:
            return "not configured"
        return next_run.strftime("%Y-%m-%d %H:%M:%S")

    def stop(self):
        """Stop the scheduler loop."""
        self._running = False


def run_with_schedule(
    task: Callable,
    schedule_time: str = "08:00",
    run_immediately: bool = True,
    timezone_name: str = "Asia/Kuala_Lumpur",
):
    """Convenience wrapper for running a daily task."""
    scheduler = Scheduler(schedule_time=schedule_time, timezone_name=timezone_name)
    scheduler.set_daily_task(task, run_immediately=run_immediately)
    scheduler.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    )

    def test_task():
        print(f"Task running... {datetime.now()}")
        time.sleep(2)
        print("Task finished")

    run_with_schedule(
        test_task,
        schedule_time="23:59",
        run_immediately=True,
        timezone_name="Asia/Kuala_Lumpur",
    )
