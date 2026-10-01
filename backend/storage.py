import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.config import PROFILE_DIR, RESUME_DIR
from backend.models import Profile

def normalize_question(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).rstrip(" *:?")

def validate_id(profile_id: str) -> str:
    try:
        return str(uuid.UUID(profile_id))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Invalid profile ID.") from exc

def profile_path(profile_id: str) -> Path:
    return PROFILE_DIR / f"{validate_id(profile_id)}.json"

def atomic_json(path: Path, data: dict) -> None:
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

def create_profile(
    profile: Profile,
    resume_bytes: bytes,
    extension: str,
    original_name: str,
) -> dict:
    profile_id = str(uuid.uuid4())
    resume_path = RESUME_DIR / f"{profile_id}{extension}"
    resume_path.write_bytes(resume_bytes)

    record = {
        "id": profile_id,
        "original_name": Path(original_name).name,
        "resume_extension": extension,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile.model_dump(),
    }

    try:
        atomic_json(profile_path(profile_id), record)
    except Exception:
        resume_path.unlink(missing_ok=True)
        raise

    return record

def get_record(profile_id: str) -> dict:
    path = profile_path(profile_id)
    if not path.exists():
        raise FileNotFoundError("Profile not found.")
    return json.loads(path.read_text(encoding="utf-8"))

def get_profile(profile_id: str) -> Profile:
    return Profile.model_validate(get_record(profile_id)["profile"])

def get_resume_path(profile_id: str) -> Path:
    record = get_record(profile_id)
    extension = record["resume_extension"]
    if extension not in {".pdf", ".docx"}:
        raise ValueError("Invalid stored resume extension.")

    path = RESUME_DIR / f"{validate_id(profile_id)}{extension}"
    if not path.exists():
        raise FileNotFoundError("Resume file not found.")
    return path

def list_profiles() -> list[dict]:
    records = []
    for path in PROFILE_DIR.glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        records.append(
            {
                "id": record["id"],
                "original_name": record["original_name"],
                "created_at": record["created_at"],
                "full_name": record["profile"]["personal"]["full_name"],
            }
        )
    return sorted(records, key=lambda item: item["created_at"], reverse=True)

def save_profile(profile_id: str, profile: Profile) -> dict:
    record = get_record(profile_id)
    profile.custom_answers = {
        normalize_question(key): value
        for key, value in profile.custom_answers.items()
        if normalize_question(key)
    }
    record["profile"] = profile.model_dump()
    atomic_json(profile_path(profile_id), record)
    return record

def remember_answer(profile_id: str, question: str, answer: str) -> None:
    profile = get_profile(profile_id)
    profile.custom_answers[normalize_question(question)] = answer
    save_profile(profile_id, profile)

def delete_profile(profile_id: str) -> None:
    resume = get_resume_path(profile_id)
    profile_path(profile_id).unlink()
    resume.unlink(missing_ok=True)