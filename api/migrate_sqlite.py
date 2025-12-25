"""One-time SQLite migration helper.

Usage (from api folder):
  python migrate_sqlite.py

It will add missing columns like stored_files.filename.
"""
from app.db import engine
from app.init_db import ensure_sqlite_schema

def main():
    ensure_sqlite_schema()
    print("OK: SQLite schema checked/updated.")

if __name__ == "__main__":
    main()
