import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, portal TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '', discovered_at TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, job_id TEXT NOT NULL,
    job_url TEXT NOT NULL, portal TEXT NOT NULL, title TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'queued',
    resume_version TEXT, run_id TEXT, confirmation_text TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    review_fields_json TEXT NOT NULL DEFAULT '[]', missing_fields_json TEXT NOT NULL DEFAULT '[]',
    sensitive_fields_json TEXT NOT NULL DEFAULT '[]', validation_errors_json TEXT NOT NULL DEFAULT '[]',
    human_approved INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS runs (\n    id TEXT PRIMARY KEY,\n    status TEXT NOT NULL DEFAULT 'queued',\n    created_at TEXT NOT NULL,\n    updated_at TEXT NOT NULL,\n    snapshot_json TEXT NOT NULL\n);\nCREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC);\n\nCREATE TABLE IF NOT EXISTS application_events (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL, event_time TEXT NOT NULL, message TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_jobs_discovered_at ON jobs(discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_portal ON jobs(portal);
CREATE INDEX IF NOT EXISTS idx_applications_created_at ON applications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_application_events_application_id ON application_events(application_id);
CREATE INDEX IF NOT EXISTS idx_application_events_time ON application_events(event_time);
"""

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def connection():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db() -> None:
    with connection() as conn:
        conn.executescript(SCHEMA)

def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

def loads(value, default):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default
