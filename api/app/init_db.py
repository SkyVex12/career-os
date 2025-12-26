
from __future__ import annotations

import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .db import DB_PATH, engine, SessionLocal
from .models import Base, Admin, User, AuthCredential, AuthToken

# NOTE: This project uses simple SQLAlchemy create_all for SQLite schema management.
# If you delete the DB file, re-run `python -m app.init_db` or start uvicorn (it calls ensure_sqlite_schema).


def ensure_sqlite_schema() -> None:
    # Create tables
    Base.metadata.create_all(bind=engine)

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
            db.add(AuthToken(token="dev-admin", principal_type="admin", principal_id="a1", principal_name="dev", created_at=now))

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    ensure_sqlite_schema()
    print(f"SQLite schema ensured at {DB_PATH}")
