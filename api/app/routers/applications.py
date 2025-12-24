from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime

from app.db import SessionLocal
from app.models import Application
from app.auth import require_extension_token

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ApplicationOut(BaseModel):
    id: int
    user_id: str
    company: str
    role: str
    url: str
    stage: str
    created_at: datetime

    class Config:
        from_attributes = True

class ApplicationUpdateIn(BaseModel):
    stage: str = Field(..., min_length=1)


@router.get("/applications/paged", dependencies=[Depends(require_extension_token)])
def list_applications_paged(
    user_id: str | None = Query(default=None, description="Optional filter by user_id"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(Application)
    if user_id:
        q = q.filter(Application.user_id == user_id)

    total = q.count()
    items = (
        q.order_by(Application.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [ApplicationOut.model_validate(x).model_dump() for x in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/applications", response_model=list[ApplicationOut], dependencies=[Depends(require_extension_token)])
def list_applications(
    user_id: str | None = Query(default=None, description="Optional filter by user_id"),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    q = db.query(Application)
    if user_id:
        q = q.filter(Application.user_id == user_id)
    items = q.order_by(Application.created_at.desc()).limit(limit).all()
    return items

@router.get("/users/{user_id}/applications", response_model=list[ApplicationOut], dependencies=[Depends(require_extension_token)])
def list_user_applications(
    user_id: str,
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    items = (
        db.query(Application)
        .filter(Application.user_id == user_id)
        .order_by(Application.created_at.desc())
        .limit(limit)
        .all()
    )
    return items

@router.get("/applications/{app_id}", response_model=ApplicationOut, dependencies=[Depends(require_extension_token)])
def get_application(app_id: int, db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "Application not found")
    return a

@router.patch("/applications/{app_id}", response_model=ApplicationOut, dependencies=[Depends(require_extension_token)])
def update_application(app_id: int, payload: ApplicationUpdateIn, db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "Application not found")
    a.stage = payload.stage
    db.commit()
    db.refresh(a)
    return a
