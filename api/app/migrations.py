from sqlalchemy import text
from sqlalchemy.engine import Engine

def _has_column(engine: Engine, table: str, column: str) -> bool:
    # SQLite pragma table_info
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table});")).fetchall()
    return any(r[1] == column for r in rows)

def migrate_sqlite(engine: Engine) -> None:
    """Lightweight schema migration for SQLite (no Alembic).
    Adds missing columns for backwards compatibility.
    """
    # applications.user_id was added after initial versions; older DBs won't have it.
    if not _has_column(engine, "applications", "user_id"):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE applications ADD COLUMN user_id TEXT;"))
            # backfill to a safe default for existing rows
            conn.execute(text("UPDATE applications SET user_id = COALESCE(user_id, 'u1');"))

    # job_descriptions.user_id
    if not _has_column(engine, "job_descriptions", "user_id"):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE job_descriptions ADD COLUMN user_id TEXT;"))
            conn.execute(text("UPDATE job_descriptions SET user_id = COALESCE(user_id, 'u1');"))

    # stored_files.user_id
    if not _has_column(engine, "stored_files", "user_id"):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE stored_files ADD COLUMN user_id TEXT;"))
            conn.execute(text("UPDATE stored_files SET user_id = COALESCE(user_id, 'u1');"))
