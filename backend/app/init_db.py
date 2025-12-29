from __future__ import annotations

import datetime as dt
import sqlite3

from sqlalchemy.orm import Session

from .db import DB_PATH, engine, SessionLocal
from .models import Base, Admin, User, AuthCredential

# NOTE: This project uses simple SQLAlchemy create_all for SQLite schema management.
# If you delete the DB file, re-run `python -m app.init_db` or start uvicorn (it calls ensure_sqlite_schema).
from .migrations import migrate_sqlite
from .models import Base, Admin, User, AuthCredential
from .security import hash_password


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _ensure_sqlite_columns() -> None:
    """Add missing columns for existing SQLite DBs.

    This project intentionally avoids Alembic; we use simple ALTER TABLE ADD COLUMN
    to keep dev setup friction low.
    """
    # Use raw sqlite3 connection so ALTER TABLE works even if SQLAlchemy has an open pool.
    conn = sqlite3.connect(DB_PATH)
    try:
        cols = _sqlite_columns(conn, "base_resumes")
        if "created_at" not in cols:
            conn.execute(
                "ALTER TABLE base_resumes ADD COLUMN created_at DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP)"
            )
        if "updated_at" not in cols:
            conn.execute(
                "ALTER TABLE base_resumes ADD COLUMN updated_at DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP)"
            )
        conn.commit()
    finally:
        conn.close()


def ensure_sqlite_schema() -> None:
    """Ensure SQLite schema exists and is up to date."""
    Base.metadata.create_all(bind=engine)
    migrate_sqlite(engine)

    # Lightweight migrations
    _ensure_sqlite_columns()

    # Seed a dev admin + token for local development (safe to run repeatedly)
    db: Session = SessionLocal()
    try:
        now = dt.datetime.utcnow()

        if db.query(Admin).first() is None:
            admin_id = "a1"
            db.add(
                Admin(
                    id=admin_id,
                    name="dev",
                    first_name="Dev",
                    last_name="Admin",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                AuthCredential(
                    email="admin@example.com",
                    password_hash=hash_password("admin"),
                    principal_type="admin",
                    principal_name="dev",
                    principal_id=admin_id,
                    created_at=now,
                )
            )

        if db.query(User).first() is None:
            user_id = "u1"
            db.add(
                User(
                    id=user_id,
                    name="User",
                    first_name="Demo",
                    last_name="User",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                AuthCredential(
                    email="user@example.com",
                    password_hash=hash_password("user"),
                    principal_type="user",
                    principal_name="User",
                    principal_id=user_id,
                    created_at=now,
                )
            )

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    ensure_sqlite_schema()
    print(f"SQLite schema ensured at {DB_PATH}")
