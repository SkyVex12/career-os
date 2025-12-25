# CareerOS Backend v2 (DOCX template + /files + multi-user base resume)

## Setup (Windows, no venv)
```powershell
py -m pip install -r requirements.txt
```

Create `.env` in project root:
```
OPENAI_API_KEY=sk-...
EXTENSION_TOKEN=your-secret
```

Run:
```powershell
py -m uvicorn main:app --reload --port 8000
```

## Set base resume for a user (required)
PUT /v1/users/{user_id}/base-resume
Header: X-Extension-Token

Body:
{ "content_text": "paste resume text..." }

## Generate tailored DOCX
POST /v1/ingest/apply-and-generate
Header: X-Extension-Token

Body:
{ "user_id":"u1","url":"...","company":"...","position":"...","jd_text":"..." }

## Re-download anytime
GET /v1/files/{file_id}
Header: X-Extension-Token


## Applications (for dashboard)
- GET /v1/applications?user_id=u1
- GET /v1/users/{user_id}/applications
- PATCH /v1/applications/{app_id}  {"stage":"interview"}


### SQLite migration note
If you upgraded from an older zip, the app will auto-add missing columns (like applications.user_id) on startup.

- GET /v1/applications/paged?user_id=u1&page=1&page_size=50

- GET /v1/applications/paged?user_id=u1&page=1&page_size=50&q=google&stage=interview&date_from=2025-12-01&date_to=2025-12-31
- GET /v1/applications/kanban?user_id=u1&stage=applied&page=1&page_size=50&q=amazon
- GET /v1/applications/stats?user_id=u1&days=60

## SQLite schema mismatch fix
If you see: `table stored_files has no column named filename`, run:

- `python migrate_sqlite.py`

Or delete your sqlite DB file to recreate it (data loss).
