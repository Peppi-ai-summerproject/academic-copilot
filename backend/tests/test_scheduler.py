import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.scheduler import (
    DailyTimeTrigger,
    DuplicateJobError,
    IntervalTrigger,
    Scheduler,
)


async def _run_and_wait_for_event(scheduler: Scheduler, event: asyncio.Event, timeout: float = 1.0):
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    finally:
        await scheduler.stop()


def test_scheduler_start_stop():
    scheduler = Scheduler(timezone="UTC")

    async def _test():
        assert not scheduler.running
        await scheduler.start()
        assert scheduler.running
        await scheduler.stop()
        assert not scheduler.running

    asyncio.run(_test())


def test_register_and_execute_job():
    event = asyncio.Event()

    async def job():
        event.set()

    async def _test():
        scheduler = Scheduler(timezone="UTC")
        await scheduler.start()

        await scheduler.register_job("test_job", job, IntervalTrigger(seconds=0.01))

        # wait for the job to run and set the event
        try:
            await asyncio.wait_for(event.wait(), timeout=1.0)
        finally:
            await scheduler.stop()

        assert event.is_set()

    asyncio.run(_test())


def test_duplicate_registration_raises():
    async def sample_job():
        return 42

    async def _test():
        scheduler = Scheduler(timezone="UTC")
        await scheduler.start()
        await scheduler.register_job("dup", sample_job, IntervalTrigger(seconds=1))
        try:
            try:
                await scheduler.register_job("dup", sample_job, IntervalTrigger(seconds=1))
                raised = False
            except DuplicateJobError:
                raised = True
        finally:
            await scheduler.stop()

        assert raised

    asyncio.run(_test())


def test_daily_trigger_uses_elapsed_time_across_helsinki_dst_transitions():
    helsinki = ZoneInfo("Europe/Helsinki")
    trigger = DailyTimeTrigger(hour=6, minute=15, tz=helsinki)

    spring_now = datetime(2026, 3, 28, 7, 0, tzinfo=helsinki)
    spring_target = datetime(2026, 3, 29, 6, 15, tzinfo=helsinki)
    autumn_now = datetime(2026, 10, 24, 7, 0, tzinfo=helsinki)
    autumn_target = datetime(2026, 10, 25, 6, 15, tzinfo=helsinki)

    assert trigger.next_run_after(spring_now) == (
        spring_target.astimezone(timezone.utc)
        - spring_now.astimezone(timezone.utc)
    ).total_seconds()
    assert trigger.next_run_after(autumn_now) == (
        autumn_target.astimezone(timezone.utc)
        - autumn_now.astimezone(timezone.utc)
    ).total_seconds()
