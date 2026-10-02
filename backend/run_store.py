import json
from pathlib import Path
from threading import Lock

from backend.config import RUN_DIR

_LOCK = Lock()


def _path(run_id: str) -> Path:
    if not run_id or "/" in run_id or "\\" in run_id:
        raise ValueError("Invalid run ID.")
    return RUN_DIR / f"{run_id}.json"


def save_run(snapshot: dict) -> None:
    with _LOCK:
        _path(snapshot["id"]).write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def get_run(run_id: str) -> dict | None:
    path = _path(run_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_runs() -> list[dict]:
    records = []
    for path in RUN_DIR.glob("*.json"):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)
