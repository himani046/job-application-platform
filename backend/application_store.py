import json
import uuid
from datetime import datetime, timezone

from backend.config import APPLICATION_DIR
from backend.database import application_key, connection, dumps, init_db, loads
from backend.models import ApplicationRecord

init_db()


def _validate_id(application_id: str):
    try:
        uuid.UUID(application_id)
    except ValueError as exc:
        raise ValueError("Invalid application ID.") from exc


def _events(conn, application_id):
    rows = conn.execute(
        """SELECT id,event_type,event_time,message,metadata_json
           FROM application_events WHERE application_id=?
           ORDER BY event_time ASC,rowid ASC""",
        (application_id,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "type": r["event_type"],
            "time": r["event_time"],
            "message": r["message"],
            "metadata": loads(r["metadata_json"], {}),
        }
        for r in rows
    ]


def _row(row, events):
    return ApplicationRecord(
        id=row["id"],
        profile_id=row["profile_id"],
        job_id=row["job_id"],
        job_url=row["job_url"],
        portal=row["portal"],
        title=row["title"],
        company=row["company"],
        status=row["status"],
        resume_version=row["resume_version"],
        run_id=row["run_id"],
        confirmation_text=row["confirmation_text"],
        application_key=row["application_key"] or application_key(
            row["profile_id"], row["portal"], row["job_id"]
        ),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        events=events,
        review_fields=loads(row["review_fields_json"], []),
        missing_fields=loads(row["missing_fields_json"], []),
        sensitive_fields=loads(row["sensitive_fields_json"], []),
        validation_errors=loads(row["validation_errors_json"], []),
        human_approved=bool(row["human_approved"]),
    )


def _upsert(conn, r):
    conn.execute(
        """INSERT INTO applications
          (id,profile_id,job_id,job_url,portal,title,company,status,resume_version,run_id,confirmation_text,
           application_key,created_at,updated_at,review_fields_json,missing_fields_json,sensitive_fields_json,
           validation_errors_json,human_approved)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET profile_id=excluded.profile_id,job_id=excluded.job_id,
          job_url=excluded.job_url,portal=excluded.portal,title=excluded.title,company=excluded.company,
          status=excluded.status,resume_version=excluded.resume_version,run_id=excluded.run_id,
          confirmation_text=excluded.confirmation_text,application_key=excluded.application_key,
          updated_at=excluded.updated_at,review_fields_json=excluded.review_fields_json,
          missing_fields_json=excluded.missing_fields_json,sensitive_fields_json=excluded.sensitive_fields_json,
          validation_errors_json=excluded.validation_errors_json,human_approved=excluded.human_approved""",
        (
            r.id,
            r.profile_id,
            r.job_id,
            r.job_url,
            r.portal,
            r.title,
            r.company,
            r.status,
            r.resume_version,
            r.run_id,
            r.confirmation_text,
            r.application_key or application_key(r.profile_id, r.portal, r.job_id),
            r.created_at,
            r.updated_at,
            dumps(r.review_fields),
            dumps(r.missing_fields),
            dumps(r.sensitive_fields),
            dumps(r.validation_errors),
            int(r.human_approved),
        ),
    )


def create_application(record):
    _validate_id(record.id)
    if not record.application_key:
        record.application_key = application_key(
            record.profile_id, record.portal, record.job_id
        )
    with connection() as conn:
        _upsert_ignore_identity(conn, record)
        row = conn.execute(
            "SELECT * FROM applications WHERE application_key=?",
            (record.application_key,),
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM applications WHERE id=?", (record.id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Application could not be persisted.")
        return _row(row, _events(conn, row["id"]))


def _upsert_ignore_identity(conn, r):
    conn.execute(
        """INSERT INTO applications
          (id,profile_id,job_id,job_url,portal,title,company,status,resume_version,run_id,confirmation_text,
           application_key,created_at,updated_at,review_fields_json,missing_fields_json,sensitive_fields_json,
           validation_errors_json,human_approved)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(application_key) DO NOTHING""",
        (
            r.id,
            r.profile_id,
            r.job_id,
            r.job_url,
            r.portal,
            r.title,
            r.company,
            r.status,
            r.resume_version,
            r.run_id,
            r.confirmation_text,
            r.application_key,
            r.created_at,
            r.updated_at,
            dumps(r.review_fields),
            dumps(r.missing_fields),
            dumps(r.sensitive_fields),
            dumps(r.validation_errors),
            int(r.human_approved),
        ),
    )


def find_application(profile_id: str, portal: str, job_id: str):
    key = application_key(profile_id, portal, job_id)
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE application_key=?",
            (key,),
        ).fetchone()
        if row is not None:
            return _row(row, _events(conn, row["id"]))
    return None


def get_application(application_id):
    _validate_id(application_id)
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE id=?", (application_id,)
        ).fetchone()
        if row is not None:
            return _row(row, _events(conn, application_id))
    path = APPLICATION_DIR / f"{application_id}.json"
    if path.exists():
        record = ApplicationRecord.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
        create_application(record)
        with connection() as conn:
            for e in record.events:
                conn.execute(
                    """INSERT OR IGNORE INTO application_events
                       (id,application_id,event_type,event_time,message,metadata_json)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        e.get("id", str(uuid.uuid4())),
                        record.id,
                        e.get("type", "unknown"),
                        e.get("time", record.updated_at),
                        e.get("message", ""),
                        dumps(e.get("metadata", {})),
                    ),
                )
        return record
    raise FileNotFoundError("Application not found.")


def update_application(record):
    _validate_id(record.id)
    if not record.application_key:
        record.application_key = application_key(
            record.profile_id, record.portal, record.job_id
        )
    record.updated_at = datetime.now(timezone.utc).isoformat()
    with connection() as conn:
        _upsert(conn, record)
        conn.execute(
            "DELETE FROM application_events WHERE application_id=?", (record.id,)
        )
        conn.executemany(
            """INSERT INTO application_events
              (id,application_id,event_type,event_time,message,metadata_json)
              VALUES (?,?,?,?,?,?)""",
            [
                (
                    e.get("id", str(uuid.uuid4())),
                    record.id,
                    e.get("type", "unknown"),
                    e.get("time", record.updated_at),
                    e.get("message", ""),
                    dumps(e.get("metadata", {})),
                )
                for e in record.events
            ],
        )
    return record


def list_applications():
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM applications ORDER BY created_at DESC,id DESC"
        ).fetchall()
        return [_row(r, _events(conn, r["id"])) for r in rows]


def record_event(record, event_type, message, **metadata):
    event = {
        "id": str(uuid.uuid4()),
        "type": event_type,
        "time": datetime.now(timezone.utc).isoformat(),
        "message": message,
        "metadata": metadata,
    }
    record.events.append(event)
    record.updated_at = datetime.now(timezone.utc).isoformat()
    if not record.application_key:
        record.application_key = application_key(
            record.profile_id, record.portal, record.job_id
        )
    with connection() as conn:
        _upsert(conn, record)
        conn.execute(
            """INSERT INTO application_events
              (id,application_id,event_type,event_time,message,metadata_json)
              VALUES (?,?,?,?,?,?)""",
            (
                event["id"],
                record.id,
                event_type,
                event["time"],
                message,
                dumps(metadata),
            ),
        )
    return record


def migrate_legacy_applications() -> int:
    count = 0
    for path in APPLICATION_DIR.glob("*.json"):
        try:
            record = ApplicationRecord.model_validate(
                json.loads(path.read_text(encoding="utf-8"))
            )
            with connection() as conn:
                if conn.execute(
                    "SELECT 1 FROM applications WHERE id=?", (record.id,)
                ).fetchone():
                    continue
                if not record.application_key:
                    record.application_key = application_key(
                        record.profile_id, record.portal, record.job_id
                    )
                existing = conn.execute(
                    "SELECT id FROM applications WHERE application_key=?",
                    (record.application_key,),
                ).fetchone()
                if existing:
                    record.application_key = f"{record.application_key}:{record.id}"
                _upsert(conn, record)
                for event in record.events:
                    conn.execute(
                        """INSERT OR IGNORE INTO application_events
                           (id,application_id,event_type,event_time,message,metadata_json)
                           VALUES (?,?,?,?,?,?)""",
                        (
                            event.get("id", str(uuid.uuid4())),
                            record.id,
                            event.get("type", "unknown"),
                            event.get("time", record.updated_at),
                            event.get("message", ""),
                            dumps(event.get("metadata", {})),
                        ),
                    )
            count += 1
        except (OSError, ValueError):
            continue
    return count


migrate_legacy_applications()
