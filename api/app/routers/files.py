import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import StoredFile
from app.auth import require_extension_token

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/files/{file_id}", dependencies=[Depends(require_extension_token)])
def download_file(file_id: int, db: Session = Depends(get_db)):
    f = db.get(StoredFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")
    if not os.path.exists(f.path):
        raise HTTPException(404, "File missing on disk")
    return FileResponse(path=f.path, media_type=f.mime, filename=f.filename)
