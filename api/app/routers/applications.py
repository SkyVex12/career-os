from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, timezone

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





@router.get("/applications/exists")
def application_exists(user_id: str, url: str, db: Session = Depends(get_db)):
    """Check if an application already exists for this user+url."""
    u = (url or "").strip()
    # normalize a little to reduce false negatives
    if u.endswith("/"):
        u = u[:-1]
    q = db.query(Application).filter(Application.user_id == user_id)
    q = q.filter(Application.url == u)
    item = q.order_by(Application.created_at.desc()).first()
    print("application_exists:", user_id, url, "found:", bool(item))
    if not item:
        return {"exists": False}
    return {
        "exists": True,
        "application": {
            "id": item.id,
            "company": item.company,
            "role": item.role,
            "url": item.url,
            "stage": item.stage,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if getattr(item, "updated_at", None) else None,
        },
    }

@router.get("/applications/stats", dependencies=[Depends(require_extension_token)])
def applications_stats(
    user_id: str | None = Query(default=None),
    days: int = Query(default=30, ge=7, le=365),
    db: Session = Depends(get_db),
):
    qset = db.query(Application)
    if user_id:
        qset = qset.filter(Application.user_id == user_id)

    stage_rows = (
        qset.with_entities(func.lower(Application.stage).label("stage"), func.count(Application.id))
        .group_by(func.lower(Application.stage))
        .all()
    )
    stage_counts = { (r[0] or "applied"): int(r[1]) for r in stage_rows }

    cutoff = datetime.now(timezone.utc) - timedelta(days=days-1)
    day_rows = (
        qset.filter(Application.created_at >= cutoff)
        .with_entities(func.strftime("%Y-%m-%d", Application.created_at).label("day"), func.count(Application.id))
        .group_by(func.strftime("%Y-%m-%d", Application.created_at))
        .order_by(func.strftime("%Y-%m-%d", Application.created_at))
        .all()
    )
    day_map = { r[0]: int(r[1]) for r in day_rows }

    series = []
    for i in range(days):
        d = (cutoff + timedelta(days=i)).date().isoformat()
        series.append({"day": d, "count": day_map.get(d, 0)})

    total = int(sum(stage_counts.values()))
    interviews = int(stage_counts.get("interview", 0))
    offers = int(stage_counts.get("offer", 0))
    rejected = int(stage_counts.get("rejected", 0))
    applied = int(stage_counts.get("applied", 0))

    return {
        "total": total,
        "stage_counts": stage_counts,
        "series_daily": series,
        "success_rate": offers / max(1, total),
        "interview_rate": interviews / max(1, total),
        "rejection_rate": rejected / max(1, total),
        "applied_count": applied,
        "interview_count": interviews,
        "offer_count": offers,
        "rejected_count": rejected,
    }

@router.get("/applications/kanban", dependencies=[Depends(require_extension_token)])
def list_applications_kanban(
    user_id: str | None = Query(default=None),
    stage: str = Query(default="applied"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    qset = db.query(Application)
    if user_id:
        qset = qset.filter(Application.user_id == user_id)
    qset = qset.filter(func.lower(Application.stage) == stage.lower())

    if q:
        like = f"%{q.strip()}%"
        qset = qset.filter(
            Application.company.ilike(like) |
            Application.role.ilike(like) |
            Application.url.ilike(like)
        )

    def _parse(d: str):
        return datetime.fromisoformat(d).replace(tzinfo=timezone.utc) if "T" in d else datetime.fromisoformat(d + "T00:00:00").replace(tzinfo=timezone.utc)

    if date_from:
        qset = qset.filter(Application.created_at >= _parse(date_from))
    if date_to:
        dt_to = datetime.fromisoformat(date_to + "T23:59:59").replace(tzinfo=timezone.utc)
        qset = qset.filter(Application.created_at <= dt_to)

    total = qset.count()
    items = (
        qset.order_by(Application.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "stage": stage.lower(),
        "items": [ApplicationOut.model_validate(x).model_dump() for x in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }

@router.get("/applications/paged", dependencies=[Depends(require_extension_token)])
def list_applications_paged(
    user_id: str | None = Query(default=None, description="Optional filter by user_id"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, description="Search company/role/url"),
    stage: str | None = Query(default=None, description="Filter stage"),
    date_from: str | None = Query(default=None, description="YYYY-MM-DD"),
    date_to: str | None = Query(default=None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    qset = db.query(Application)
    if user_id:
        qset = qset.filter(Application.user_id == user_id)
    if stage:
        qset = qset.filter(func.lower(Application.stage) == stage.lower())
    if q:
        like = f"%{q.strip()}%"
        qset = qset.filter(
            Application.company.ilike(like) |
            Application.role.ilike(like) |
            Application.url.ilike(like)
        )

    def _parse(d: str):
        return datetime.fromisoformat(d).replace(tzinfo=timezone.utc) if "T" in d else datetime.fromisoformat(d + "T00:00:00").replace(tzinfo=timezone.utc)

    if date_from:
        qset = qset.filter(Application.created_at >= _parse(date_from))
    if date_to:
        dt_to = datetime.fromisoformat(date_to + "T23:59:59").replace(tzinfo=timezone.utc)
        qset = qset.filter(Application.created_at <= dt_to)

    total = qset.count()

    items = (
        qset.order_by(Application.created_at.desc())
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
    items = qset.order_by(Application.created_at.desc()).limit(limit).all()
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
