from pathlib import Path
from datetime import datetime
import re

BASE_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def safe_filename(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^A-Za-z0-9_\-\.]+", "", s)
    return s[:80] or "file"


def save_bytes(user_id: str, application_id: int, filename: str, data: bytes) -> Path:
    app_dir = STORAGE_DIR / user_id / str(application_id)
    app_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = app_dir / f"{ts}_{filename}"
    path.write_bytes(data)
    return path
