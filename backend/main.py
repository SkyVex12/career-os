from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.init_db import ensure_schema
from app.routers import (
    auth_routes,
    users,
    applications,
    ingest,
    files,
    assistant,
    jd,
    resume_builder,
    outlook,
    email_updates,
    gate,
)


app = FastAPI(title="CareerOS API")

# Dev CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    ensure_schema()


# Routers
app.include_router(auth_routes.router)
app.include_router(users.router)
app.include_router(applications.router)
app.include_router(ingest.router)
app.include_router(files.router)
app.include_router(assistant.router)
app.include_router(jd.router)
app.include_router(resume_builder.router)
app.include_router(outlook.router)
app.include_router(email_updates.router)
app.include_router(gate.router)

@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/readyz")
def readyz():
    # Basic readiness: DB connection works
    try:
        from app.db import SessionLocal
        db = SessionLocal()
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
