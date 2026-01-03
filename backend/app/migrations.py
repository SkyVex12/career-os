from sqlalchemy import text
from sqlalchemy.engine import Engine


def _has_table(engine: Engine, table: str) -> bool:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": table},
        ).fetchall()
    return len(rows) > 0


def _has_column(engine: Engine, table: str, column: str) -> bool:
    # SQLite pragma table_info
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table});")).fetchall()
    return any(r[1] == column for r in rows)


def migrate_sqlite(engine: Engine) -> None:
    """Lightweight schema migration for SQLite (no Alembic).
    Adds missing columns for backwards compatibility.
    """

    # outlook integrations + email event tables
    if not _has_table(engine, "outlook_integrations"):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
            CREATE TABLE IF NOT EXISTS outlook_integrations (
                user_id TEXT PRIMARY KEY,
                account_email TEXT,
                access_token TEXT,
                refresh_token TEXT,
                expires_at DATETIME,
                last_sync_at DATETIME,
                auto_update INTEGER DEFAULT 0,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            """
                )
            )
    if not _has_table(engine, "email_events"):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
            CREATE TABLE IF NOT EXISTS email_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'outlook',
                message_id TEXT NOT NULL,
                internet_message_id TEXT,
                from_email TEXT,
                subject TEXT,
                received_at DATETIME,
                body_preview TEXT,
                web_link TEXT,
                raw_json TEXT,
                created_at DATETIME NOT NULL,
                CONSTRAINT uq_email_user_provider_internetid UNIQUE (user_id, provider, internet_message_id)
            );
            """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_email_events_user_id ON email_events(user_id);"
                )
            )
    if not _has_table(engine, "application_update_suggestions"):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
            CREATE TABLE IF NOT EXISTS application_update_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                application_id TEXT,
                email_event_id INTEGER NOT NULL,
                suggested_stage TEXT NOT NULL,
                confidence INTEGER DEFAULT 0,
                reason TEXT,
                status TEXT DEFAULT 'pending',
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY(email_event_id) REFERENCES email_events(id)
            );
            """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_app_update_sugg_user_id ON application_update_suggestions(user_id);"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_app_update_sugg_app_id ON application_update_suggestions(application_id);"
                )
            )
    # applications.user_id was added after initial versions; older DBs won't have it.
    if not _has_column(engine, "applications", "user_id"):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE applications ADD COLUMN user_id TEXT;"))
            # backfill to a safe default for existing rows
            conn.execute(
                text("UPDATE applications SET user_id = COALESCE(user_id, 'u1');")
            )

    # job_descriptions.user_id
    if not _has_column(engine, "job_descriptions", "user_id"):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE job_descriptions ADD COLUMN user_id TEXT;"))
            conn.execute(
                text("UPDATE job_descriptions SET user_id = COALESCE(user_id, 'u1');")
            )

    # applications.source_site (human-entered source site name: indeed, linkedin, etc.)
    if not _has_column(engine, "applications", "source_site"):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE applications ADD COLUMN source_site TEXT;"))

        # stored_files.user_id
        if not _has_column(engine, "stored_files", "user_id"):
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE stored_files ADD COLUMN user_id TEXT;"))
                conn.execute(
                    text("UPDATE stored_files SET user_id = COALESCE(user_id, 'u1');")
                )
