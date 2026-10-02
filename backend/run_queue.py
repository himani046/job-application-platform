import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Awaitable, Callable

from backend.config import QUEUE_STATE_PATH, WORKER_LEASE_SECONDS


@dataclass(order=True)
class QueueItem:
    priority: int
    sequence: int
    run_id: str = field(compare=False)


class RunQueue:
    """Persistent priority queue with restart recovery and worker leases."""

    def __init__(self, worker_count: int = 2, state_path: Path = QUEUE_STATE_PATH, lease_seconds: int = WORKER_LEASE_SECONDS):
        self.worker_count = max(1, worker_count)
        self.state_path = state_path
        self.lease_seconds = max(30, lease_seconds)
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._workers: list[asyncio.Task] = []
        self._sequence = 0
        self._handler: Callable[[str], Awaitable[None]] | None = None
        self._state_lock = Lock()
        self._items: dict[str, dict] = {}

    def _read_state(self) -> dict:
        if not self.state_path.exists():
            return {"items": {}}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"items": {}}

    def _write_state(self) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"items": self._items}, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)

    def _persist(self) -> None:
        with self._state_lock:
            self._write_state()

    def bind(self, handler: Callable[[str], Awaitable[None]]) -> None:
        self._handler = handler

    async def start(self) -> None:
        if self._workers:
            return
        state = self._read_state()
        self._items = state.get("items", {})
        for item in self._items.values():
            if item.get("status") == "running":
                item["status"] = "queued"
                item["lease_until"] = None
                item["recovered_at"] = datetime.now(timezone.utc).isoformat()
        self._sequence = max([int(i.get("sequence", 0)) for i in self._items.values()] or [0])
        self._persist()
        for item in self._items.values():
            if item.get("status") == "queued":
                await self._queue.put(QueueItem(int(item.get("priority", 100)), int(item.get("sequence", 0)), item["run_id"]))
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"application-worker-{index}")
            for index in range(self.worker_count)
        ]

    async def put(self, run_id: str, priority: int = 100) -> None:
        self._sequence += 1
        self._items[run_id] = {
            "run_id": run_id, "priority": priority, "sequence": self._sequence,
            "status": "queued", "lease_until": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._persist()
        await self._queue.put(QueueItem(priority, self._sequence, run_id))

    def cancel(self, run_id: str) -> bool:
        item = self._items.get(run_id)
        if not item or item.get("status") != "queued":
            return False
        item["status"] = "cancelled"
        item["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        self._persist()
        return True

    async def _claim(self, run_id: str) -> bool:
        item = self._items.get(run_id)
        if not item or item.get("status") != "queued":
            return False
        item["status"] = "running"
        item["worker_id"] = str(uuid.uuid4())
        item["started_at"] = datetime.now(timezone.utc).isoformat()
        item["lease_until"] = datetime.now(timezone.utc).timestamp() + self.lease_seconds
        self._persist()
        return True

    async def _heartbeat(self, run_id: str) -> None:
        interval = max(10, self.lease_seconds // 3)
        while True:
            await asyncio.sleep(interval)
            item = self._items.get(run_id)
            if not item or item.get("status") != "running":
                return
            item["lease_until"] = datetime.now(timezone.utc).timestamp() + self.lease_seconds
            self._persist()

    async def _worker(self, index: int) -> None:
        while True:
            item = await self._queue.get()
            heartbeat = None
            try:
                if await self._claim(item.run_id) and self._handler:
                    heartbeat = asyncio.create_task(self._heartbeat(item.run_id))
                    await self._handler(item.run_id)
                    self.mark_complete(item.run_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.mark_failed(item.run_id)
            finally:
                if heartbeat:
                    heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)
                self._queue.task_done()

    def mark_complete(self, run_id: str) -> None:
        self._items.pop(run_id, None)
        self._persist()

    def mark_failed(self, run_id: str) -> None:
        item = self._items.get(run_id)
        if item:
            item["status"] = "failed"
            item["lease_until"] = None
            item["failed_at"] = datetime.now(timezone.utc).isoformat()
            self._persist()

    def size(self) -> int:
        return sum(1 for i in self._items.values() if i.get("status") == "queued")

    def snapshot(self) -> dict:
        return {
            "workers": self.worker_count,
            "running_workers": sum(not task.done() for task in self._workers),
            "queued": self.size(),
            "leased": sum(1 for i in self._items.values() if i.get("status") == "running"),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    async def shutdown(self) -> None:
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
