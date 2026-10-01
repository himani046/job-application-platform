import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

raw_data_dir = Path(os.getenv("DATA_DIR", "./data")).expanduser()
DATA_DIR = (
    raw_data_dir.resolve()
    if raw_data_dir.is_absolute()
    else (ROOT / raw_data_dir).resolve()
)

PROFILE_DIR = DATA_DIR / "profiles"
RESUME_DIR = DATA_DIR / "resumes"
BROWSER_DIR = DATA_DIR / "browsers"

for directory in (DATA_DIR, PROFILE_DIR, RESUME_DIR, BROWSER_DIR):
    directory.mkdir(parents=True, exist_ok=True)

API_TOKEN = os.getenv("LOCAL_API_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

ENABLE_STEALTH = os.getenv("ENABLE_STEALTH", "false").lower() == "true"
HUMAN_TIMEOUT_SECONDS = int(os.getenv("HUMAN_TIMEOUT_SECONDS", "1800"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024