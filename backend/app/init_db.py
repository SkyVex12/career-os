from __future__ import annotations

import datetime as dt
import sqlite3

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .db import DB_PATH, engine, SessionLocal
from .models import Base, Admin, User, AuthCredential, AuthToken


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

# NOTE: This project uses simple SQLAlchemy create_all for SQLite schema management.
# If you delete the DB file, re-run `python -m app.init_db` or start uvicorn (it calls ensure_sqlite_schema).


def ensure_sqlite_schema() -> None:
    # Create tables
    Base.metadata.create_all(bind=engine)

    # Lightweight migrations
    _ensure_sqlite_columns()

    # Seed a dev admin + token for local development (safe to run repeatedly)
    db: Session = SessionLocal()
    try:
        now = dt.datetime.utcnow()

        admin = db.query(Admin).filter(Admin.id == "a1").first()
        if not admin:
            admin = Admin(id="a1", name="Dev Admin")
            db.add(admin)

        # Add a dev token that the extension can use by default
        tok = db.query(AuthToken).filter(AuthToken.token == "dev-admin").first()
        if not tok:
            db.add(
                AuthToken(
                    token="dev-admin",
                    principal_type="admin",
                    principal_id="a1",
                    principal_name="dev",
                    created_at=now,
                )
            )

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    ensure_sqlite_schema()
    print(f"SQLite schema ensured at {DB_PATH}")
