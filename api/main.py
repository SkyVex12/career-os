
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.init_db import ensure_sqlite_schema
from app.routers import auth_routes, users, applications, ingest, files


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
    ensure_sqlite_schema()


# Routers
app.include_router(auth_routes.router)
app.include_router(users.router)
app.include_router(applications.router)
app.include_router(ingest.router)
app.include_router(files.router)
