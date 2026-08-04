import asyncio
from app.services.scheduler import Scheduler, IntervalTrigger, DuplicateJobError

async def test_start_stop():
    s = Scheduler(timezone='UTC')
    print('running before', s.running)
    await s.start()
    print('running after start', s.running)
    await s.stop()
    print('running after stop', s.running)

async def test_register_and_execute():
    event = asyncio.Event()
    async def job():
        print('job executed')
        event.set()
    s = Scheduler(timezone='UTC')
    await s.start()
    await s.register_job('t1', job, IntervalTrigger(seconds=0.01))
    try:
        await asyncio.wait_for(event.wait(), timeout=1.0)
        print('event seen')
    finally:
        await s.stop()

async def test_duplicate():
    async def sample_job():
        return 1
    s = Scheduler(timezone='UTC')
    await s.start()
    await s.register_job('dup', sample_job, IntervalTrigger(seconds=0.1))
    try:
        try:
            await s.register_job('dup', sample_job, IntervalTrigger(seconds=0.1))
            print('duplicate not raised')
        except DuplicateJobError:
            print('duplicate raised')
    finally:
        await s.stop()

async def main():
    await test_start_stop()
    await test_register_and_execute()
    await test_duplicate()

if __name__ == '__main__':
    asyncio.run(main())
