import asyncio
import tempfile
import unittest
from pathlib import Path

from backend.run_queue import RunQueue
from backend.scheduler import Scheduler


class DurableQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_queue_state_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.json"
            queue = RunQueue(worker_count=1, state_path=path, lease_seconds=30)
            await queue.put("run-1", priority=7)

            restarted = RunQueue(worker_count=1, state_path=path, lease_seconds=30)
            self.assertEqual(restarted.size(), 0)
            await restarted.start()
            self.assertEqual(restarted.size(), 1)
            await restarted.shutdown()

    async def test_cancel_prevents_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.json"
            queue = RunQueue(worker_count=1, state_path=path, lease_seconds=30)
            await queue.put("run-1")
            self.assertTrue(queue.cancel("run-1"))

            called = asyncio.Event()

            async def handler(_run_id):
                called.set()

            queue.bind(handler)
            await queue.start()
            await asyncio.sleep(0.05)
            self.assertFalse(called.is_set())
            await queue.shutdown()
    async def test_two_queue_instances_atomic_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            import backend.database as database
            original = database.DATABASE_PATH
            database.DATABASE_PATH = Path(tmp) / "platform.db"
            try:
                database.init_db()
                first = RunQueue(worker_count=1, lease_seconds=30)
                second = RunQueue(worker_count=1, lease_seconds=30)
                await first.put("run-atomic", priority=1)
                claims = []

                async def handler(run_id):
                    claims.append(run_id)

                first.bind(handler)
                second.bind(handler)
                await asyncio.gather(first.start(), second.start())
                await asyncio.sleep(0.2)
                self.assertEqual(claims, ["run-atomic"])
                await first.shutdown()
                await second.shutdown()
            finally:
                database.DATABASE_PATH = original



class DurableSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_schedule_survives_restart_and_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "schedule.json"
            async def enqueue(_run_id, _priority):
                return None

            scheduler = Scheduler(enqueue, state_path=path)
            await scheduler.schedule("run-1", "2099-01-01T00:00:00+00:00", 4)
            restarted = Scheduler(enqueue, state_path=path)
            await restarted.start()
            self.assertEqual(restarted.snapshot()["scheduled"], 1)
            self.assertTrue(await restarted.cancel("run-1"))
            self.assertEqual(restarted.snapshot()["scheduled"], 0)
            await restarted.shutdown()


if __name__ == "__main__":
    unittest.main()
