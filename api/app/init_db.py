from __future__ import annotations
from pathlib import Path
import sqlite3
from datetime import datetime
import secrets, hashlib, base64

from .db import engine, Base, DATABASE_URL, DATA_DIR
from . import models  # noqa

def _sqlite_path_from_url(url: str) -> str | None:
    if not url.startswith("sqlite"):
        return None
    # sqlite:///relative or sqlite:////abs
    p = url.replace("sqlite:////", "", 1).replace("sqlite:///", "", 1)
    return str(Path(p))

def _has_column(cur, table: str, col: str) -> bool:
    cur.execute(f"PRAGMA table_info({table});")
    return any(r[1] == col for r in cur.fetchall())

def _pbkdf2_hash(password: str, *, iterations: int = 210_000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
    return "pbkdf2_sha256$%d$%s$%s" % (
        iterations,
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(dk).decode("ascii").rstrip("="),
    )

def ensure_sqlite_schema() -> None:
    db_path = _sqlite_path_from_url(DATABASE_URL)
    if not db_path:
        return
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        # Ensure tables exist (create_all below). Here only add columns to old tables.
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='applications';")
        if cur.fetchone():
            if not _has_column(cur, "applications", "updated_at"):
                cur.execute("ALTER TABLE applications ADD COLUMN updated_at DATETIME;")
                cur.execute("UPDATE applications SET updated_at = created_at WHERE updated_at IS NULL;")

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stored_files';")
        if cur.fetchone():
            if not _has_column(cur, "stored_files", "filename"):
                cur.execute("ALTER TABLE stored_files ADD COLUMN filename TEXT;")
                cur.execute("UPDATE stored_files SET filename = 'file' WHERE filename IS NULL;")

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='admins';")
        if cur.fetchone():
            if not _has_column(cur, "admins", "name"):
                cur.execute("ALTER TABLE admins ADD COLUMN name TEXT;")
            if not _has_column(cur, "admins", "first_name"):
                cur.execute("ALTER TABLE admins ADD COLUMN first_name TEXT;")
            if not _has_column(cur, "admins", "last_name"):
                cur.execute("ALTER TABLE admins ADD COLUMN last_name TEXT;")
            if not _has_column(cur, "admins", "dob"):
                cur.execute("ALTER TABLE admins ADD COLUMN dob TEXT;")

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        if cur.fetchone():
            if not _has_column(cur, "users", "admin_id"):
                cur.execute("ALTER TABLE users ADD COLUMN admin_id TEXT;")
            if not _has_column(cur, "users", "name"):
                cur.execute("ALTER TABLE users ADD COLUMN name TEXT;")
            if not _has_column(cur, "users", "first_name"):
                cur.execute("ALTER TABLE users ADD COLUMN first_name TEXT;")
            if not _has_column(cur, "users", "last_name"):
                cur.execute("ALTER TABLE users ADD COLUMN last_name TEXT;")
            if not _has_column(cur, "users", "dob"):
                cur.execute("ALTER TABLE users ADD COLUMN dob TEXT;")
# credentials (email/password) for dev
        admin_pw = _pbkdf2_hash("admin123")
        user_pw = _pbkdf2_hash("user123")
        cur.execute("INSERT OR IGNORE INTO auth_credentials (email, password_hash, principal_type, principal_id, created_at) VALUES (?,?,?,?,?);",
                    ("admin@local", admin_pw, "admin", "a1", datetime.utcnow().isoformat()))
        cur.execute("INSERT OR IGNORE INTO auth_credentials (email, password_hash, principal_type, principal_id, created_at) VALUES (?,?,?,?,?);",
                    ("u1@local", user_pw, "user", "u1", datetime.utcnow().isoformat()))
        conn.commit()
    finally:
        conn.close()

def seed_dev_data() -> None:
    """Seed a1 admin + a couple of users + tokens if missing."""
    db_path = _sqlite_path_from_url(DATABASE_URL)
    if not db_path:
        return
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # admins
        cur.execute("INSERT OR IGNORE INTO admins (id, name) VALUES (?,?);", ("a1","Admin"))
        # users
        cur.execute("INSERT OR IGNORE INTO users (id, admin_id, name) VALUES (?,?,?);", ("u1","a1","User 1"))
        cur.execute("INSERT OR IGNORE INTO users (id, admin_id, name) VALUES (?,?,?);", ("u2","a1","User 2"))
        # tokens
        cur.execute("SELECT COUNT(1) FROM auth_tokens WHERE token=?;", ("dev-admin",))
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO auth_tokens (token, principal_type, principal_id, created_at) VALUES (?,?,?,?);",
                ("dev-admin","admin","a1", datetime.utcnow().isoformat())
            )
        cur.execute("SELECT COUNT(1) FROM auth_tokens WHERE token=?;", ("dev-u1",))
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO auth_tokens (token, principal_type, principal_id, created_at) VALUES (?,?,?,?);",
                ("dev-u1","user","u1", datetime.utcnow().isoformat())
            )

        # credentials (email/password) for dev
        admin_pw = _pbkdf2_hash("admin123")
        user_pw = _pbkdf2_hash("user123")
        cur.execute("INSERT OR IGNORE INTO auth_credentials (email, password_hash, principal_type, principal_id, created_at) VALUES (?,?,?,?,?);",
                    ("admin@local", admin_pw, "admin", "a1", datetime.utcnow().isoformat()))
        cur.execute("INSERT OR IGNORE INTO auth_credentials (email, password_hash, principal_type, principal_id, created_at) VALUES (?,?,?,?,?);",
                    ("u1@local", user_pw, "user", "u1", datetime.utcnow().isoformat()))
        conn.commit()
    finally:
        conn.close()

def init_db() -> None:
    ensure_sqlite_schema()
    Base.metadata.create_all(bind=engine)
    seed_dev_data()
