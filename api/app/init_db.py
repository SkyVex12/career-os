from .db import engine, Base
from . import models  # noqa
from app.migrations import migrate_sqlite

import sqlite3
from pathlib import Path
from datetime import datetime

def ensure_sqlite_schema(database_url: str) -> None:
    """Lightweight migration for SQLite: add new columns without Alembic."""
    if not database_url.startswith("sqlite"):
        return

    # sqlite:///relative/path.db OR sqlite:////absolute/path.db
    db_path = database_url.replace("sqlite:///", "", 1)
    db_path = db_path.replace("sqlite:////", "", 1)
    db_path = str(Path(db_path))
    if not db_path:
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        def has_column(table: str, column: str) -> bool:
            cur.execute(f"PRAGMA table_info({table});")
            cols = [r[1] for r in cur.fetchall()]
            return column in cols

        # stored_files: filename column introduced later
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stored_files';")
        if cur.fetchone():
            if not has_column("stored_files", "filename"):
                cur.execute("ALTER TABLE stored_files ADD COLUMN filename TEXT;")

        # applications: updated_at column for legacy DBs
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='applications';")
        if cur.fetchone():
            if not has_column("applications", "updated_at"):
                cur.execute("ALTER TABLE applications ADD COLUMN updated_at DATETIME;")
                # backfill updated_at with created_at where possible
                try:
                    cur.execute("UPDATE applications SET updated_at = created_at WHERE updated_at IS NULL;")
                except Exception:
                    pass

        conn.commit()
    finally:
        conn.close()
Base.metadata.create_all(bind=engine)
migrate_sqlite(engine)
