from __future__ import annotations

import datetime as dt
import os

from sqlalchemy.orm import Session
from sqlalchemy import text

from .db import engine, SessionLocal
from .models import Base, Admin, User, AuthCredential
from .security import hash_password


# Only import sqlite-specific migration if we're actually using sqlite
def _is_sqlite() -> bool:
    try:
        return engine.dialect.name == "sqlite"
    except Exception:
        return False


def ensure_schema() -> None:
    """Ensure schema exists (SQLite or Postgres)."""
    # Create tables for any DB
    Base.metadata.create_all(bind=engine)

    # SQLite-only lightweight migrations
    if _is_sqlite():
        import sqlite3
        from .db import DB_PATH
        from .migrations import migrate_sqlite

        migrate_sqlite(engine)

        # Lightweight SQLite column adds
        conn = sqlite3.connect(DB_PATH)
        try:
            rows = conn.execute("PRAGMA table_info(base_resumes)").fetchall()
            cols = {r[1] for r in rows}
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

    # Optional seed (works for Postgres too)
    # NOTE: You may want to disable seeding in production.
    seed = os.getenv("SEED_DEV_USERS", "0") == "1"
    if seed:
        db: Session = SessionLocal()
        try:
            now = dt.datetime.now()

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
    ensure_schema()
    print(f"Schema ensured. Dialect={engine.dialect.name}")
