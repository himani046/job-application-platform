import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from backend.config import APPLICATION_DIR
from backend.models import ApplicationRecord


_LOCK = Lock()


def _path(application_id: str) -> Path:
    try:
        uuid.UUID(application_id)
    except ValueError as exc:
        raise ValueError("Invalid application ID.") from exc
    return APPLICATION_DIR / f"{application_id}.json"


def create_application(record: ApplicationRecord) -> ApplicationRecord:
    with _LOCK:
        path = _path(record.id)
        path.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return record


def get_application(application_id: str) -> ApplicationRecord:
    path = _path(application_id)
    if not path.exists():
        raise FileNotFoundError("Application not found.")
    return ApplicationRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))


def update_application(record: ApplicationRecord) -> ApplicationRecord:
    with _LOCK:
        record.updated_at = datetime.now(timezone.utc).isoformat()
        _path(record.id).write_text(
            json.dumps(record.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return record


def list_applications() -> list[ApplicationRecord]:
    records = []
    for path in APPLICATION_DIR.glob("*.json"):
        try:
            records.append(ApplicationRecord.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    return sorted(records, key=lambda item: item.created_at, reverse=True)


def record_event(record: ApplicationRecord, event_type: str, message: str, **metadata) -> ApplicationRecord:
    record.events.append(
        {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "time": datetime.now(timezone.utc).isoformat(),
            "message": message,
            "metadata": metadata,
        }
    )
    return update_application(record)
