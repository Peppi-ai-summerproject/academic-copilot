"""Lightweight in-process scheduler used by the Autonomous Workflow Engine.

Design goals (minimal, dependency-free):
- Start/stop with explicit lifecycle control.
- Register recurring jobs with IntervalTrigger or DailyTimeTrigger.
- Respect explicit timezone configured via Settings.
- Prevent duplicate job registration by default.
- Be usable in tests without starting the FastAPI app.

This module intentionally avoids external dependencies so it can be
included without changing requirements.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from typing import Any, Awaitable, Callable, Dict, Optional

CallableOrCoro = Callable[..., Any]

logger = logging.getLogger("academic-copilot.scheduler")


class SchedulerError(RuntimeError):
    pass


class DuplicateJobError(SchedulerError):
    pass


class Trigger:
    """Base trigger interface.

    Implementors must provide next_run_after(now) -> seconds (float >= 0)
    representing how many seconds from now the trigger's next firing should
    occur.
    """

    def next_run_after(self, now: datetime) -> float:
        raise NotImplementedError


@dataclass
class IntervalTrigger(Trigger):
    seconds: float

    def next_run_after(self, now: datetime) -> float:
        return max(0.0, float(self.seconds))


@dataclass
class DailyTimeTrigger(Trigger):
    """Run every day at a specific local time. Optionally limit to days_of_week
    where Monday is 0 and Sunday is 6.

    This is a minimal replacement for cron/daily scheduling for the MVP.
    """

    hour: int
    minute: int = 0
    second: int = 0
    days_of_week: Optional[set[int]] = None
    tz: ZoneInfo | None = None

    def next_run_after(self, now: datetime) -> float:
        tz = self.tz or now.tzinfo or ZoneInfo("UTC")
        localized_now = now.astimezone(tz)

        today_target = datetime(
            localized_now.year,
            localized_now.month,
            localized_now.day,
            self.hour,
            self.minute,
            self.second,
            tzinfo=tz,
        )

        # If the time today is not yet reached, schedule today; otherwise tomorrow
        candidate = today_target if localized_now < today_target else today_target + timedelta(days=1)

        # If days_of_week constraint provided, advance until matching day
        if self.days_of_week is not None:
            attempts = 0
            while candidate.weekday() not in self.days_of_week:
                candidate += timedelta(days=1)
                attempts += 1
                if attempts > 8:
                    raise SchedulerError("DailyTimeTrigger: no matching weekday found")

        # Convert both values to a fixed-offset timezone before subtracting.
        # Subtracting two datetimes that share one ZoneInfo object uses wall
        # time and can be an hour wrong across a daylight-saving transition.
        delta = (
            candidate.astimezone(timezone.utc)
            - localized_now.astimezone(timezone.utc)
        ).total_seconds()
        return max(0.0, delta)


@dataclass
class Job:
    job_id: str
    func: CallableOrCoro
    trigger: Trigger
    task: Optional[asyncio.Task] = None


class Scheduler:
    def __init__(self, timezone: str = "UTC", logger_: Optional[logging.Logger] = None):
        try:
            self._tz = ZoneInfo(timezone)
        except Exception:
            # zoneinfo may be unavailable in minimal environments (no tzdata)
            # Fall back to a simple UTC tzinfo to keep scheduler functional in
            # test or developer environments without requiring extra packages.
            logger.warning("ZoneInfo(%s) not available, falling back to UTC", timezone)
            from datetime import timezone as _dt_timezone

            self._tz = _dt_timezone.utc

        self._jobs: Dict[str, Job] = {}
        self._running = False
        self._lock = asyncio.Lock()
        self._stopped = asyncio.Event()
        self._logger = logger_ or logger

    @property
    def timezone(self) -> str:
        # ZoneInfo objects expose a 'key' attribute. datetime.timezone fallback
        # objects do not, so use a safe getattr with default.
        return getattr(self._tz, "key", "UTC")

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        async with self._lock:
            if self._running:
                self._logger.info("Scheduler already running")
                return

            self._logger.info("Starting scheduler (tz=%s)", getattr(self._tz, "key", "UTC"))
            self._running = True
            self._stopped.clear()

            # Spawn per-job loops
            for job in list(self._jobs.values()):
                job.task = asyncio.create_task(self._job_loop(job))

            self._logger.info("Scheduler started with %d job(s)", len(self._jobs))

    async def stop(self) -> None:
        async with self._lock:
            if not self._running:
                self._logger.info("Scheduler not running")
                return

            self._logger.info("Stopping scheduler")
            self._running = False

            # Cancel running job tasks
            tasks = [job.task for job in self._jobs.values() if job.task]
            for t in tasks:
                if t and not t.done():
                    t.cancel()

            # Wait for tasks to finish
            if tasks:
                await asyncio.gather(*[t for t in tasks if t], return_exceptions=True)

            self._stopped.set()
            self._logger.info("Scheduler stopped")

    async def register_job(self, job_id: str, func: CallableOrCoro, trigger: Trigger, replace_existing: bool = False) -> None:
        if not callable(func):
            raise TypeError("func must be callable")

        async with self._lock:
            if job_id in self._jobs and not replace_existing:
                self._logger.warning("Duplicate job registration attempt: %s", job_id)
                raise DuplicateJobError(f"Job with id '{job_id}' is already registered")

            job = Job(job_id=job_id, func=func, trigger=trigger)
            self._jobs[job_id] = job

            self._logger.info("Job registered: %s", job_id)

            if self._running:
                # start job loop
                job.task = asyncio.create_task(self._job_loop(job))

    async def unregister_job(self, job_id: str) -> None:
        async with self._lock:
            job = self._jobs.pop(job_id, None)
            if not job:
                return
            if job.task and not job.task.done():
                job.task.cancel()
                try:
                    await job.task
                except asyncio.CancelledError:
                    pass

            self._logger.info("Job unregistered: %s", job_id)

    async def _job_loop(self, job: Job) -> None:
        """Background loop for a single job. Computes next run delay using the
        job.trigger.next_run_after() and executes the job callable. Exceptions
        are logged but do not stop the loop.
        """
        self._logger.info("Job loop started: %s", job.job_id)
        try:
            while self._running:
                now = datetime.now(tz=self._tz)
                try:
                    delay = float(job.trigger.next_run_after(now))
                except Exception as e:
                    self._logger.exception("Error computing next run for job %s: %s", job.job_id, e)
                    # avoid tight loop on trigger errors
                    await asyncio.sleep(1)
                    continue

                # ensure we don't sleep negative or too tightly
                if delay > 0:
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        break

                # Execute the job
                try:
                    if inspect.iscoroutinefunction(job.func):
                        await job.func()
                    else:
                        # run sync functions in default thread pool to avoid blocking loop
                        await asyncio.get_running_loop().run_in_executor(None, job.func)

                except asyncio.CancelledError:
                    break
                except Exception:
                    self._logger.exception("Job %s raised an exception during execution", job.job_id)

        finally:
            self._logger.info("Job loop stopped: %s", job.job_id)
