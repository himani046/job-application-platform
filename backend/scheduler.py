import asyncio
import json
import heapq
from datetime import datetime, timezone
from pathlib import Path

from backend.config import SCHEDULE_STATE_PATH
from backend.database import connection, init_db


class Scheduler:
    """SQLite-backed scheduler. Scheduled records survive backend restarts."""

    def __init__(self, enqueue, state_path: Path = SCHEDULE_STATE_PATH):
        self.enqueue = enqueue
        self.state_path = state_path
        self.items = []
        self.task = None
        self._sequence = 0

    def _legacy_state(self) -> list[dict]:
        if not self.state_path.exists():
            return []
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _migrate_legacy_state(self) -> None:
        with connection() as conn:
            for item in self._legacy_state():
                try:
                    when = datetime.fromisoformat(item["scheduled_at"].replace("Z", "+00:00"))
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    sequence = int(item.get("sequence", 0))
                    self._sequence = max(self._sequence, sequence)
                    conn.execute(
                        """INSERT INTO scheduled_runs(run_id,scheduled_at,priority,sequence)
                           VALUES (?,?,?,?) ON CONFLICT(run_id) DO NOTHING""",
                        (
                            item["run_id"], when.isoformat(),
                            int(item.get("priority", 100)), sequence,
                        ),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
        if self.state_path.exists():
            migrated = self.state_path.with_suffix(".migrated.json")
            try:
                self.state_path.replace(migrated)
            except OSError:
                pass

    async def start(self) -> None:
        if self.task:
            return
        init_db()
        self._migrate_legacy_state()
        with connection() as conn:
            rows = conn.execute(
                "SELECT run_id,scheduled_at,priority,sequence FROM scheduled_runs "
                "ORDER BY scheduled_at,sequence"
            ).fetchall()
        self.items = []
        for row in rows:
            try:
                when = datetime.fromisoformat(row["scheduled_at"].replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                self._sequence = max(self._sequence, int(row["sequence"]))
                heapq.heappush(
                    self.items,
                    (when.timestamp(), int(row["sequence"]), row["run_id"], int(row["priority"])),
                )
            except (TypeError, ValueError):
                continue
        self.task = asyncio.create_task(self._loop(), name="run-scheduler")

    async def schedule(self, run_id: str, scheduled_at: str, priority: int = 100):
        when = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        self._sequence += 1
        with connection() as conn:
            conn.execute(
                """INSERT INTO scheduled_runs(run_id,scheduled_at,priority,sequence)
                   VALUES (?,?,?,?)
                   ON CONFLICT(run_id) DO UPDATE SET
                     scheduled_at=excluded.scheduled_at,
                     priority=excluded.priority,
                     sequence=excluded.sequence""",
                (run_id, when.isoformat(), priority, self._sequence),
            )
        heapq.heappush(self.items, (when.timestamp(), self._sequence, run_id, priority))

    async def cancel(self, run_id: str) -> bool:
        with connection() as conn:
            result = conn.execute(
                "DELETE FROM scheduled_runs WHERE run_id=?", (run_id,)
            )
        self.items = [item for item in self.items if item[2] != run_id]
        heapq.heapify(self.items)
        return result.rowcount > 0

    async def _loop(self):
        while True:
            try:
                with connection() as conn:
                    row = conn.execute(
                        """SELECT run_id,scheduled_at,priority FROM scheduled_runs
                           ORDER BY scheduled_at,sequence LIMIT 1"""
                    ).fetchone()
                if not row:
                    await asyncio.sleep(0.5)
                    continue
                when = datetime.fromisoformat(row["scheduled_at"].replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                delay = when.timestamp() - datetime.now(timezone.utc).timestamp()
                if delay > 0:
                    await asyncio.sleep(min(delay, 5))
                    continue
                run_id = row["run_id"]
                with connection() as conn:
                    deleted = conn.execute(
                        "DELETE FROM scheduled_runs WHERE run_id=? AND scheduled_at=?",
                        (run_id, row["scheduled_at"]),
                    )
                if deleted.rowcount:
                    await self.enqueue(run_id, int(row["priority"]))
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(0.5)

    async def shutdown(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    def snapshot(self):
        with connection() as conn:
            rows = conn.execute(
                "SELECT run_id,scheduled_at,priority FROM scheduled_runs "
                "ORDER BY scheduled_at,sequence"
            ).fetchall()
        return {
            "scheduled": len(rows),
            "items": [
                {
                    "run_id": row["run_id"],
                    "scheduled_at": row["scheduled_at"],
                    "priority": int(row["priority"]),
                }
                for row in rows
            ],
        }
