from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

def save_bytes(user_id: str, application_id: int, filename: str, data: bytes) -> str:
    app_dir = STORAGE_DIR / user_id / str(application_id)
    app_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = app_dir / f"{ts}_{filename}"
    path.write_bytes(data)
    return str(path)
