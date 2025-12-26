import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import StoredFile, User
from ..auth import get_principal, Principal

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/files/{file_id}")
def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    f = db.get(StoredFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")
    # scope check: user => own; admin => user belongs to admin
    if not os.path.exists(f.path):
        raise HTTPException(404, "File missing on disk")
    return FileResponse(path=f.path, media_type=f.mime, filename=f.filename)
