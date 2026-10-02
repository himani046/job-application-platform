import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from backend.config import QUEUE_STATE_PATH, WORKER_LEASE_SECONDS
from backend.database import connection, init_db


@dataclass(order=True)
class QueueItem:
    priority: int
    sequence: int
    run_id: str = field(compare=False)


class RunQueue:
    """SQLite-backed priority queue with atomic claims and worker leases."""

    def __init__(self, worker_count: int = 2, state_path: Path = QUEUE_STATE_PATH, lease_seconds: int = WORKER_LEASE_SECONDS):
        self.worker_count = max(1, worker_count)
        self.state_path = state_path
        self.lease_seconds = max(30, lease_seconds)
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._workers: list[asyncio.Task] = []
        self._sequence = 0
        self._handler: Callable[[str], Awaitable[None]] | None = None
        self._seen_run_ids: set[str] = set()

    def _legacy_state(self) -> dict:
        if not self.state_path.exists():
            return {"items": {}}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"items": {}}

    def _migrate_legacy_state(self) -> None:
        state = self._legacy_state()
        with connection() as conn:
            for item in state.get("items", {}).values():
                run_id = item.get("run_id")
                if not run_id:
                    continue
                sequence = int(item.get("sequence", 0))
                self._sequence = max(self._sequence, sequence)
                status = item.get("status", "queued")
                if status == "running":
                    status = "queued"
                    recovered_at = datetime.now(timezone.utc).isoformat()
                else:
                    recovered_at = item.get("recovered_at")
                conn.execute(
                    """INSERT INTO queue_items
                       (run_id,priority,sequence,status,worker_id,lease_until,created_at,recovered_at,cancelled_at)
                       VALUES (?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(run_id) DO NOTHING""",
                    (
                        run_id, int(item.get("priority", 100)), sequence, status,
                        None, None, item.get("created_at", datetime.now(timezone.utc).isoformat()),
                        recovered_at, item.get("cancelled_at"),
                    ),
                )
        if self.state_path.exists():
            migrated = self.state_path.with_suffix(".migrated.json")
            try:
                self.state_path.replace(migrated)
            except OSError:
                pass

    def bind(self, handler: Callable[[str], Awaitable[None]]) -> None:
        self._handler = handler

    async def start(self) -> None:
        if self._workers:
            return
        init_db()
        self._migrate_legacy_state()
        now = datetime.now(timezone.utc).timestamp()
        with connection() as conn:
            conn.execute(
                """UPDATE queue_items
                   SET status='queued', worker_id=NULL, lease_until=NULL, recovered_at=?
                   WHERE status='running' AND (lease_until IS NULL OR lease_until < ?)""",
                (datetime.now(timezone.utc).isoformat(), now),
            )
            rows = conn.execute(
                """SELECT run_id,priority,sequence FROM queue_items
                   WHERE status='queued' ORDER BY priority,sequence"""
            ).fetchall()
            self._sequence = max([int(r["sequence"]) for r in rows] + [self._sequence, 0])
        self._seen_run_ids.clear()
        for row in rows:
            self._seen_run_ids.add(row["run_id"])
            await self._queue.put(QueueItem(int(row["priority"]), int(row["sequence"]), row["run_id"]))
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"application-worker-{index}")
            for index in range(self.worker_count)
        ]

    async def put(self, run_id: str, priority: int = 100) -> None:
        self._sequence += 1
        now = datetime.now(timezone.utc).isoformat()
        with connection() as conn:
            row = conn.execute("SELECT status FROM queue_items WHERE run_id=?", (run_id,)).fetchone()
            if row and row["status"] in {"queued", "running"}:
                return
            conn.execute(
                """INSERT INTO queue_items
                   (run_id,priority,sequence,status,created_at)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(run_id) DO UPDATE SET
                     priority=excluded.priority,sequence=excluded.sequence,status='queued',
                     worker_id=NULL,lease_until=NULL,cancelled_at=NULL""",
                (run_id, priority, self._sequence, "queued", now),
            )
        await self._queue.put(QueueItem(priority, self._sequence, run_id))

    def cancel(self, run_id: str) -> bool:
        with connection() as conn:
            result = conn.execute(
                """UPDATE queue_items SET status='cancelled', cancelled_at=?
                   WHERE run_id=? AND status='queued'""",
                (datetime.now(timezone.utc).isoformat(), run_id),
            )
        return result.rowcount > 0

    async def _claim(self, run_id: str) -> bool:
        worker_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        lease_until = now.timestamp() + self.lease_seconds
        with connection() as conn:
            result = conn.execute(
                """UPDATE queue_items
                   SET status='running',worker_id=?,started_at=?,lease_until=?
                   WHERE run_id=? AND status='queued'""",
                (worker_id, now.isoformat(), lease_until, run_id),
            )
        return result.rowcount > 0

    async def _heartbeat(self, run_id: str) -> None:
        interval = max(10, self.lease_seconds // 3)
        while True:
            await asyncio.sleep(interval)
            with connection() as conn:
                conn.execute(
                    """UPDATE queue_items SET lease_until=?
                       WHERE run_id=? AND status='running'""",
                    (datetime.now(timezone.utc).timestamp() + self.lease_seconds, run_id),
                )

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
        with connection() as conn:
            conn.execute(
                """UPDATE queue_items SET status='completed',lease_until=NULL,completed_at=?
                   WHERE run_id=?""",
                (datetime.now(timezone.utc).isoformat(), run_id),
            )

    def mark_failed(self, run_id: str) -> None:
        with connection() as conn:
            conn.execute(
                """UPDATE queue_items SET status='failed',lease_until=NULL,failed_at=?
                   WHERE run_id=?""",
                (datetime.now(timezone.utc).isoformat(), run_id),
            )

    def size(self) -> int:
        with connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) AS n FROM queue_items WHERE status='queued'"
            ).fetchone()["n"]

    def snapshot(self) -> dict:
        with connection() as conn:
            leased = conn.execute(
                "SELECT COUNT(*) AS n FROM queue_items WHERE status='running'"
            ).fetchone()["n"]
        return {
            "workers": self.worker_count,
            "running_workers": sum(not task.done() for task in self._workers),
            "queued": self.size(),
            "leased": leased,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    async def shutdown(self) -> None:
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
