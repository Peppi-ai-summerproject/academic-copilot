Scheduler infrastructure (Issue #100)

What it does
- Provides a minimal in-process scheduler used by the Autonomous Workflow Engine.
- Supports registering recurring jobs and runs them on a background asyncio task.
- Intentionally lightweight and dependency-free for the initial MVP.

What it does NOT do
- Does not implement academic workflows or business logic.
- Does not provide distributed, persistent, or fault-tolerant scheduling.
- Does not persist job state across restarts.

How it starts and stops
- The scheduler is started during the FastAPI application's lifespan if
  `settings.scheduler_enabled` is True.
- It is created and started in the application's lifespan context so no
  scheduler is started at import time.
- On shutdown the scheduler is stopped and background tasks are cancelled.

How to enable or disable
- The scheduler is disabled by default. Enable it by setting the
  environment variable used by Settings (see app/core/config.py) for
  `scheduler_enabled=true` and optionally `scheduler_timezone`.

Timezone behavior
- The scheduler uses the IANA timezone name from `scheduler_timezone`.
- Defaults to "UTC".
- Triggers receive the scheduler's timezone when computing next run times.

How to register jobs
- Use the Scheduler API (example):

  async def some_work():
      ...

  scheduler = Scheduler(timezone=settings.scheduler_timezone)
  await scheduler.start()
  await scheduler.register_job(
      job_id="my_job",
      func=some_work,
      trigger=IntervalTrigger(seconds=60),
  )

- Jobs can be synchronous or async callables. Synchronous callables are
  executed in the default thread pool so they do not block the event loop.

Testing
- Tests use small interval triggers and asyncio Events to deterministically
  verify execution without long sleeps.
- The scheduler is disabled by default in tests by keeping
  `scheduler_enabled=false` so tests do not start uncontrolled background
  work.

Limitations and future work
- Add cron-like parsing or adopt APScheduler for full cron support and
  richer features when dependency policy allows.
- Persist job definitions if needed for multi-instance deployments.
- Add leader election and distributed locking for multi-instance safety.
