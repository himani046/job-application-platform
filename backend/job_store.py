import json
from datetime import datetime, timezone

from backend.config import JOB_DIR
from backend.database import connection, init_db
from backend.models import JobRecord

init_db()

def _row(row) -> JobRecord:
    return JobRecord(
        id=row["id"], portal=row["portal"], title=row["title"], url=row["url"],
        company=row["company"], location=row["location"], description=row["description"],
        discovered_at=row["discovered_at"], metadata=json.loads(row["metadata_json"] or "{}"),
    )

def upsert_job(job: JobRecord) -> JobRecord:
    with connection() as conn:
        conn.execute(
            """INSERT INTO jobs
            (id,portal,title,url,company,location,description,discovered_at,metadata_json,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET portal=excluded.portal,title=excluded.title,
            url=excluded.url,company=excluded.company,location=excluded.location,
            description=excluded.description,discovered_at=excluded.discovered_at,
            metadata_json=excluded.metadata_json""",
            (job.id,job.portal,job.title,job.url,job.company,job.location,job.description,
             job.discovered_at,json.dumps(job.metadata,ensure_ascii=False),
             job.discovered_at or datetime.now(timezone.utc).isoformat()),
        )
    return job

def get_job(job_id: str) -> JobRecord:
    with connection() as conn:
        row=conn.execute("SELECT * FROM jobs WHERE id=?",(job_id,)).fetchone()
    if row is not None:
        return _row(row)
    path=JOB_DIR/f"{job_id}.json"
    if path.exists():
        job=JobRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
        upsert_job(job)
        return job
    raise FileNotFoundError("Job not found.")

def list_jobs() -> list[JobRecord]:
    with connection() as conn:
        rows=conn.execute("SELECT * FROM jobs ORDER BY discovered_at DESC,id DESC").fetchall()
    return [_row(row) for row in rows]

def upsert_jobs(jobs: list[JobRecord]) -> list[JobRecord]:
    if not jobs: return []
    with connection() as conn:
        conn.executemany(
            """INSERT INTO jobs
            (id,portal,title,url,company,location,description,discovered_at,metadata_json,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET portal=excluded.portal,title=excluded.title,
            url=excluded.url,company=excluded.company,location=excluded.location,
            description=excluded.description,discovered_at=excluded.discovered_at,
            metadata_json=excluded.metadata_json""",
            [(j.id,j.portal,j.title,j.url,j.company,j.location,j.description,j.discovered_at,
              json.dumps(j.metadata,ensure_ascii=False),
              j.discovered_at or datetime.now(timezone.utc).isoformat()) for j in jobs],
        )
    return jobs

def migrate_legacy_jobs() -> int:
    count=0
    for path in JOB_DIR.glob("*.json"):
        try:
            upsert_job(JobRecord.model_validate(json.loads(path.read_text(encoding="utf-8"))))
            count+=1
        except (OSError,ValueError): continue
    return count

migrate_legacy_jobs()
