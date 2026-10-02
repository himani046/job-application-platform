import asyncio
import hmac
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.job_store import get_job, list_jobs, upsert_jobs
from backend.analytics import summarize_applications
from backend.run_queue import RunQueue
from backend.scheduler import Scheduler
from backend.jobs import job_fingerprint, normalize_job
from backend.matcher import rank_jobs
from backend.application_store import (
    create_application,
    get_application,
    list_applications,
    record_event,
    update_application,
)
from backend.config import API_TOKEN, MAX_RUN_HISTORY, MAX_UPLOAD_BYTES
from backend.engine import Engine, Run, start_url, validate_public_url
from backend.run_store import list_runs as list_persisted_runs, save_run
from backend.models import (
    ApplicationRecord,
    JobMatchRequest,
    Profile,
    RunCommand,
    RunRequest,
)
from backend.parser import parse_resume
from backend.portals import list_adapters
from backend.storage import (
    create_profile,
    delete_profile,
    get_profile,
    get_record,
    get_resume_path,
    list_profiles,
    save_profile,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunManager:
    """In-process orchestration layer.

    Runs may execute concurrently when they target different portals. A portal
    still has one active browser run at a time because persistent Chromium
    profiles are portal-scoped.
    """

    def __init__(self):
        self.runs: dict[str, Run] = {}
        self.active_by_portal: dict[str, str] = {}
        self.portal_locks: dict[str, asyncio.Lock] = {}

    def get(self, run_id: str) -> Run:
        run = self.runs.get(run_id)
        if run is None:
            raise HTTPException(404, "Run not found.")
        return run

    def start(
        self,
        request: RunRequest,
        profile: Profile | None,
        resume_path: Path | None,
        application_id: str | None = None,
    ) -> Run:
        while len(self.runs) >= MAX_RUN_HISTORY:
            oldest_id = next(iter(self.runs))
            if oldest_id in self.active_by_portal.values():
                break
            self.runs.pop(oldest_id)

        run = Run(id=str(uuid.uuid4()), request=request)
        run.application_id = application_id
        self.runs[run.id] = run
        save_run(run.snapshot())
        return run

    def recover(self) -> list[str]:
        cancelled = []
        for snapshot in list_persisted_runs():
            run_id = snapshot.get("id")
            if not run_id or run_id in self.runs:
                continue
            try:
                run = Run(id=run_id, request=RunRequest.model_validate(snapshot["request"]))
            except (KeyError, ValueError):
                continue
            run.status = snapshot.get("status", "queued")
            run.created_at = snapshot.get("created_at", run.created_at)
            run.application_id = snapshot.get("application_id")
            run.results = snapshot.get("results", [])
            run.pending = snapshot.get("pending")
            for item in snapshot.get("logs", [])[-800:]:
                run.logs.append(item)
            self.runs[run.id] = run
            if run.status == "running":
                if run.application_id:
                    try:
                        application = get_application(run.application_id)
                        application.status = "submission_uncertain"
                        record_event(application, "worker_recovery", "Backend restarted while the browser run was active; automatic replay was blocked.")
                    except (FileNotFoundError, ValueError):
                        pass
                    run.status = "failed"
                    save_run(run.snapshot())
                    cancelled.append(run.id)
                else:
                    run.status = "queued"
                    save_run(run.snapshot())
        return cancelled

    async def drive_queued(self, run_id: str) -> None:
        run = self.runs.get(run_id)
        if not run or run.status != "queued":
            return
        profile = None
        resume_path = None
        if run.request.mode == "apply":
            try:
                profile = get_profile(run.request.profile_id or "")
                resume_path = get_resume_path(run.request.profile_id or "")
            except (ValueError, FileNotFoundError) as exc:
                run.status = "failed"
                run.log(f"Queued run could not load its profile: {exc}", "error")
                return
        run.task = asyncio.current_task()
        lock = self.portal_locks.setdefault(run.request.portal, asyncio.Lock())
        async with lock:
            self.active_by_portal[run.request.portal] = run.id
            save_run(run.snapshot())
            if run.application_id:
                try:
                    application = get_application(run.application_id)
                    record_event(application, "run_started", "Browser worker started execution.")
                except (FileNotFoundError, ValueError):
                    pass
            await self.drive(run, profile, resume_path)

    async def drive(
        self,
        run: Run,
        profile: Profile | None,
        resume_path: Path | None,
    ) -> None:
        try:
            run.status = "running"
            save_run(run.snapshot())
            await Engine(run, profile, resume_path).execute()

            if run.request.mode == "discover" and run.results:
                jobs = [
                    normalize_job(item, run.request.portal)
                    for item in run.results
                    if item.get("url")
                ]
                upsert_jobs(jobs)
                run.results = [
                    job.model_dump(mode="json")
                    for job in jobs
                ]
                run.log(
                    f"Persisted {len(jobs)} normalized jobs for future matching."
                )
        except asyncio.CancelledError:
            run.status = "stopped"
            run.log("Run stopped by the user.", "warning")
        except asyncio.TimeoutError:
            run.status = "expired"
            run.log(
                "The human-response deadline expired; the browser was closed.",
                "warning",
            )
        except Exception as exc:
            run.status = "failed"
            run.log(
                f"{type(exc).__name__}: {str(exc)[:1000]}",
                "error",
            )
        finally:
            run.pending = None
            save_run(run.snapshot())
            if self.active_by_portal.get(run.request.portal) == run.id:
                self.active_by_portal.pop(run.request.portal, None)

            if run.application_id:
                try:
                    application = get_application(run.application_id)
                    application.status = {
                        "stopped": "stopped",
                        "expired": "failed",
                        "failed": "failed",
                    }.get(run.status, application.status)
                    application.run_id = run.id
                    record_event(
                        application,
                        "run_finished",
                        f"Browser run finished with status '{run.status}'.",
                        run_status=run.status,
                    )
                except (FileNotFoundError, ValueError):
                    pass

    async def shutdown(self) -> None:
        tasks = [
            run.task
            for run in self.runs.values()
            if run.task and not run.task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


manager = RunManager()
queue = RunQueue(worker_count=2)
scheduler = Scheduler(queue.put)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if len(API_TOKEN) < 24:
        raise RuntimeError(
            "Configure LOCAL_API_TOKEN with at least 24 characters in .env."
        )
    queue.bind(manager.drive_queued)
    recovered = manager.recover()
    await queue.start()
    for run_id in recovered:
        queue.cancel(run_id)
    await scheduler.start()
    yield
    await scheduler.shutdown()
    await queue.shutdown()
    await manager.shutdown()


app = FastAPI(
    title="Local Job Application Platform",
    version="2.2.0",
    lifespan=lifespan,
)


def authenticate(
    x_api_token: str | None = Header(default=None),
) -> None:
    if not x_api_token or not hmac.compare_digest(x_api_token, API_TOKEN):
        raise HTTPException(401, "Invalid API token.")


auth = [Depends(authenticate)]


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": app.version,
        "active_portals": list(manager.active_by_portal),
    }


@app.get("/portals", dependencies=auth)
async def portals():
    return list_adapters()


@app.get("/profiles", dependencies=auth)
async def profiles():
    return list_profiles()


@app.post("/profiles/upload", dependencies=auth)
async def upload_profile(file: UploadFile = File(...)):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".pdf", ".docx"}:
        raise HTTPException(400, "Upload a PDF or DOCX resume.")

    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()

    if not content:
        raise HTTPException(400, "The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The uploaded file exceeds the configured limit.")

    try:
        profile = await asyncio.to_thread(parse_resume, content, extension)
        return create_profile(
            profile,
            content,
            extension,
            file.filename or f"resume{extension}",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            502,
            f"Resume parsing failed: {type(exc).__name__}: {str(exc)[:500]}",
        ) from exc


@app.get("/profiles/{profile_id}", dependencies=auth)
async def read_profile(profile_id: str):
    try:
        return get_record(profile_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.put("/profiles/{profile_id}", dependencies=auth)
async def update_profile(profile_id: str, profile: Profile):
    try:
        return save_profile(profile_id, profile)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/profiles/{profile_id}/resume", dependencies=auth)
async def download_resume(profile_id: str):
    try:
        record = get_record(profile_id)
        path = get_resume_path(profile_id)
        return FileResponse(path, filename=record["original_name"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.delete("/profiles/{profile_id}", dependencies=auth)
async def remove_profile(profile_id: str):
    try:
        delete_profile(profile_id)
        return {"deleted": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/applications", dependencies=auth)
async def applications():
    return [item.model_dump(mode="json") for item in list_applications()]


@app.get("/analytics/applications", dependencies=auth)
async def application_analytics():
    return summarize_applications(list_applications())


@app.get("/queue", dependencies=auth)
async def queue_status():
    return {"queue": queue.snapshot(), "scheduler": scheduler.snapshot(), "active_portals": dict(manager.active_by_portal)}


@app.get("/schedules", dependencies=auth)
async def schedules():
    return scheduler.snapshot()


@app.get("/jobs", dependencies=auth)
async def jobs():
    return [item.model_dump(mode="json") for item in list_jobs()]


@app.get("/jobs/{job_id}", dependencies=auth)
async def read_job(job_id: str):
    try:
        return get_job(job_id).model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/jobs/match", dependencies=auth)
async def match_jobs(request: JobMatchRequest):
    try:
        profile = get_profile(request.profile_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    return rank_jobs(profile, list_jobs(), request.limit)


@app.get("/applications/{application_id}", dependencies=auth)
async def read_application(application_id: str):
    try:
        return get_application(application_id).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/runs", dependencies=auth)
async def create_run(request: RunRequest):
    if request.mode == "apply" and not request.job_url:
        raise HTTPException(400, "Application mode requires a specific job URL.")
    if request.mode == "login" and request.headless:
        raise HTTPException(400, "Interactive session setup requires headed mode.")

    profile = None
    resume_path = None
    application_id = None

    if request.mode == "apply":
        if not request.profile_id:
            raise HTTPException(400, "Select a saved profile.")
        try:
            profile = get_profile(request.profile_id)
            resume_path = get_resume_path(request.profile_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    try:
        await validate_public_url(start_url(request))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if request.mode == "apply":
        application_id = str(uuid.uuid4())
        now = utc_now()
        record = ApplicationRecord(
            id=application_id,
            profile_id=request.profile_id,
            job_id=job_fingerprint(request.job_url or "", ""),
            job_url=request.job_url or "",
            portal=request.portal,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        create_application(record)
        record_event(record, "queued", "Application queued for browser execution.")

    run = manager.start(
        request,
        profile,
        resume_path,
        application_id=application_id,
    )

    if request.scheduled_at:
        try:
            await scheduler.schedule(run.id, request.scheduled_at, request.priority)
            run.log(f"Run scheduled for {request.scheduled_at}.")
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f"Invalid scheduled_at: {exc}") from exc
    else:
        await queue.put(run.id, request.priority)
        run.log(f"Run queued with priority {request.priority}.")

    if application_id:
        record = get_application(application_id)
        record.run_id = run.id
        record_event(record, "scheduled" if request.scheduled_at else "queued", "Application scheduled." if request.scheduled_at else "Application queued for a worker.")

    return run.snapshot()


@app.get("/runs", dependencies=auth)
async def list_runs():
    return {
        "active_ids": dict(manager.active_by_portal),
        "runs": [
            {
                "id": run.id,
                "status": run.status,
                "created_at": run.created_at,
                "request": run.request.model_dump(),
                "application_id": run.application_id,
            }
            for run in reversed(list(manager.runs.values()))
        ],
    }


@app.get("/runs/{run_id}", dependencies=auth)
async def read_run(run_id: str):
    return manager.get(run_id).snapshot()


@app.post("/runs/{run_id}/commands", dependencies=auth)
async def command_run(run_id: str, command: RunCommand):
    run = manager.get(run_id)

    if command.action == "stop":
        if run.status == "queued" and (not run.task or run.task.done()):
            run.status = "stopped"
            queue.cancel(run.id)
            await scheduler.cancel(run.id)
            save_run(run.snapshot())
            if run.application_id:
                try:
                    application = get_application(run.application_id)
                    application.status = "stopped"
                    record_event(application, "stopped", "Queued run cancelled before browser execution.")
                except (FileNotFoundError, ValueError):
                    pass
            return {"accepted": True}
        if not run.task or run.task.done():
            raise HTTPException(409, "This run is no longer active.")
        run.task.cancel()
        return {"accepted": True}

    if not run.task or run.task.done():
        raise HTTPException(409, "This run is no longer active.")

    pending = run.pending
    if not pending or run.status != "waiting":
        raise HTTPException(409, "The run is not waiting for a human response.")
    if command.pause_token != pending["token"]:
        raise HTTPException(409, "This response belongs to an outdated pause.")
    if pending["claimed"]:
        raise HTTPException(409, "A response to this pause is already being processed.")
    if command.action not in pending["allowed"]:
        raise HTTPException(400, "This action is not allowed at the current pause.")
    if command.action == "answer" and not (command.answer or "").strip():
        raise HTTPException(400, "Enter a non-empty answer.")

    pending["claimed"] = True
    if command.action == "mark_submitted" and run.application_id:
        try:
            application = get_application(run.application_id)
            application.status = "submitted"
            application.human_approved = True
            record_event(application, "submitted", "Candidate verified the application receipt and marked it submitted.")
        except (FileNotFoundError, ValueError):
            pass
    run.queue.put_nowait(command)
    return {"accepted": True}
