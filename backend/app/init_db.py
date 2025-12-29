from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from .db import DB_PATH, engine, SessionLocal
from .migrations import migrate_sqlite
from .models import Base, Admin, User, AuthCredential
from .security import hash_password


def ensure_sqlite_schema() -> None:
    """Ensure SQLite schema exists and is up to date."""
    Base.metadata.create_all(bind=engine)
    migrate_sqlite(engine)

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
