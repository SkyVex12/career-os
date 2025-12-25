from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.init_db import init_db
from app.routers.ingest import router as ingest_router
from app.routers.files import router as files_router
from app.routers.base_resume import router as base_resume_router
from app.routers.applications import router as applications_router
from app.routers.users import router as users_router
from app.routers.auth_routes import router as auth_router

init_db()

app = FastAPI(title="CareerOS Backend (Admin + Multi-user + Batch Apply)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/v1", tags=["auth"])
app.include_router(users_router, prefix="/v1", tags=["users"])
app.include_router(ingest_router, prefix="/v1", tags=["ingest"])
app.include_router(files_router, prefix="/v1", tags=["files"])
app.include_router(base_resume_router, prefix="/v1", tags=["base-resume"])
app.include_router(applications_router, prefix="/v1", tags=["applications"])

@app.get("/health")
def health():
    return {"ok": True}
