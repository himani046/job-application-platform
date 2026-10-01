import json
from threading import Lock

from backend.config import JOB_DIR
from backend.models import JobRecord


_LOCK = Lock()


def _path(job_id: str):
    return JOB_DIR / f"{job_id}.json"


def upsert_job(job: JobRecord) -> JobRecord:
    with _LOCK:
        _path(job.id).write_text(
            json.dumps(job.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return job


def get_job(job_id: str) -> JobRecord:
    path = _path(job_id)
    if not path.exists():
        raise FileNotFoundError("Job not found.")
    return JobRecord.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )


def list_jobs() -> list[JobRecord]:
    records = []
    for path in JOB_DIR.glob("*.json"):
        try:
            records.append(
                JobRecord.model_validate(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            )
        except (OSError, ValueError):
            continue
    return sorted(
        records,
        key=lambda item: item.discovered_at,
        reverse=True,
    )


def upsert_jobs(jobs: list[JobRecord]) -> list[JobRecord]:
    return [upsert_job(job) for job in jobs]
