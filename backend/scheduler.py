import asyncio
import heapq
from datetime import datetime, timezone


class Scheduler:
    def __init__(self, enqueue):
        self.enqueue = enqueue
        self.items = []
        self.task = None
        self._sequence = 0

    async def start(self):
        if not self.task:
            self.task = asyncio.create_task(self._loop(), name="run-scheduler")

    async def schedule(self, run_id: str, scheduled_at: str):
        when = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        self._sequence += 1
        heapq.heappush(self.items, (when.timestamp(), self._sequence, run_id))

    async def _loop(self):
        while True:
            if not self.items:
                await asyncio.sleep(0.5)
                continue
            timestamp, _, run_id = self.items[0]
            delay = timestamp - datetime.now(timezone.utc).timestamp()
            if delay > 0:
                await asyncio.sleep(min(delay, 5))
                continue
            heapq.heappop(self.items)
            await self.enqueue(run_id)

    async def shutdown(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    def snapshot(self):
        return {
            "scheduled": len(self.items),
            "items": [
                {"run_id": run_id, "scheduled_at": datetime.fromtimestamp(ts, timezone.utc).isoformat()}
                for ts, _, run_id in sorted(self.items)
            ],
        }
