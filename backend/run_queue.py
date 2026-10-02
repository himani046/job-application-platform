import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable


@dataclass(order=True)
class QueueItem:
    priority: int
    sequence: int
    run_id: str = field(compare=False)


class RunQueue:
    """Small in-process worker queue with bounded concurrent workers.

    Browser sessions remain portal-scoped and are serialized by RunManager;
    the queue controls when a run receives a worker rather than creating a
    second browser for the same persistent portal profile.
    """

    def __init__(self, worker_count: int = 2):
        self.worker_count = max(1, worker_count)
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._workers: list[asyncio.Task] = []
        self._sequence = 0
        self._handler: Callable[[str], Awaitable[None]] | None = None

    def bind(self, handler: Callable[[str], Awaitable[None]]) -> None:
        self._handler = handler

    async def start(self) -> None:
        if self._workers:
            return
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"application-worker-{index}")
            for index in range(self.worker_count)
        ]

    async def put(self, run_id: str, priority: int = 100) -> None:
        self._sequence += 1
        await self._queue.put(QueueItem(priority, self._sequence, run_id))

    async def _worker(self, index: int) -> None:
        while True:
            item = await self._queue.get()
            try:
                if self._handler:
                    await self._handler(item.run_id)
            finally:
                self._queue.task_done()

    def size(self) -> int:
        return self._queue.qsize()

    async def shutdown(self) -> None:
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    def snapshot(self) -> dict:
        return {
            "workers": self.worker_count,
            "running_workers": sum(not task.done() for task in self._workers),
            "queued": self.size(),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
