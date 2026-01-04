from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import StoredFile
from ..auth import get_principal, Principal

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/files/{file_id}")
@router.get("/v1/files/{file_id}")
@router.get("/v1/files/{file_id}/download")
def download_file(
    file_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    f = db.get(StoredFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")

    # f.path is now a Cloudinary secure URL
    return RedirectResponse(f.path)
