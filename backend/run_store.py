import json
from datetime import datetime, timezone

from backend.database import connection, init_db

init_db()

def save_run(snapshot: dict) -> None:
    now=datetime.now(timezone.utc).isoformat()
    created=snapshot.get("created_at",now)
    with connection() as conn:
        conn.execute("""INSERT INTO runs(id,status,created_at,updated_at,snapshot_json)
                        VALUES(?,?,?,?,?)
                        ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                        updated_at=excluded.updated_at,snapshot_json=excluded.snapshot_json""",
                     (snapshot["id"],snapshot.get("status","queued"),created,now,
                      json.dumps(snapshot,ensure_ascii=False)))

def get_run(run_id: str) -> dict | None:
    if not run_id or "/" in run_id or "\\" in run_id:
        raise ValueError("Invalid run ID.")
    with connection() as conn:
        row=conn.execute("SELECT snapshot_json FROM runs WHERE id=?",(run_id,)).fetchone()
    return json.loads(row["snapshot_json"]) if row else None

def list_runs() -> list[dict]:
    with connection() as conn:
        rows=conn.execute("SELECT snapshot_json FROM runs ORDER BY created_at DESC,id DESC").fetchall()
    return [json.loads(row["snapshot_json"]) for row in rows]


def migrate_legacy_runs(run_dir) -> int:
    count = 0
    for path in run_dir.glob("*.json"):
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            if snapshot.get("id") and get_run(snapshot["id"]) is None:
                save_run(snapshot)
                count += 1
        except (OSError, ValueError):
            continue
    return count
