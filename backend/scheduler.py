import asyncio
import heapq
import json
from datetime import datetime, timezone
from pathlib import Path

from backend.config import SCHEDULE_STATE_PATH


class Scheduler:
    """Persistent scheduler. Scheduled records survive backend restarts."""

    def __init__(self, enqueue, state_path: Path = SCHEDULE_STATE_PATH):
        self.enqueue = enqueue
        self.state_path = state_path
        self.items = []
        self.task = None
        self._sequence = 0

    def _read_state(self) -> list[dict]:
        if not self.state_path.exists():
            return []
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _persist(self) -> None:
        payload = [
            {"run_id": run_id, "scheduled_at": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
             "priority": priority, "sequence": sequence}
            for ts, sequence, run_id, priority in self.items
        ]
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)

    async def start(self) -> None:
        if self.task:
            return
        self.items = []
        for item in self._read_state():
            try:
                when = datetime.fromisoformat(item["scheduled_at"].replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                sequence = int(item.get("sequence", 0))
                self._sequence = max(self._sequence, sequence)
                heapq.heappush(self.items, (when.timestamp(), sequence, item["run_id"], int(item.get("priority", 100))))
            except (KeyError, TypeError, ValueError):
                continue
        self._persist()
        self.task = asyncio.create_task(self._loop(), name="run-scheduler")

    async def schedule(self, run_id: str, scheduled_at: str, priority: int = 100):
        when = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        self._sequence += 1
        heapq.heappush(self.items, (when.timestamp(), self._sequence, run_id, priority))
        self._persist()

    async def cancel(self, run_id: str) -> bool:
        before = len(self.items)
        self.items = [item for item in self.items if item[2] != run_id]
        heapq.heapify(self.items)
        changed = len(self.items) != before
        if changed:
            self._persist()
        return changed

    async def _loop(self):
        while True:
            if not self.items:
                await asyncio.sleep(0.5)
                continue
            timestamp, _, run_id, priority = self.items[0]
            delay = timestamp - datetime.now(timezone.utc).timestamp()
            if delay > 0:
                await asyncio.sleep(min(delay, 5))
                continue
            heapq.heappop(self.items)
            self._persist()
            await self.enqueue(run_id, priority)

    async def shutdown(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    def snapshot(self):
        return {
            "scheduled": len(self.items),
            "items": [
                {"run_id": run_id, "scheduled_at": datetime.fromtimestamp(ts, timezone.utc).isoformat(), "priority": priority}
                for ts, _, run_id, priority in sorted(self.items)
            ],
        }
