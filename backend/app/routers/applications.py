from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field

from ..auth import Principal, get_db, get_principal
from ..models import Application, AdminUser, Admin, User

router = APIRouter(prefix="/v1", tags=["applications"])


class ApplicationOut(BaseModel):
    id: str
    user_id: str
    company: str
    role: str
    url: str
    stage: str
    created_at: dt.datetime

    class Config:
        from_attributes = True


class ApplicationUpdateIn(BaseModel):
    stage: str = Field(..., min_length=1)


def _scoped_query(db: Session, principal: Principal):
    q = db.query(Application)
    if principal.type == "user":
        q = q.filter(Application.user_id == principal.id)
    else:
        q = q.join(AdminUser, AdminUser.user_id == Application.user_id).filter(
            AdminUser.admin_id == principal.id
        )
    return q


def _admin_can_access_user(db: Session, admin_id: str, user_id: str) -> bool:
    return (
        db.query(AdminUser)
        .filter(AdminUser.admin_id == admin_id, AdminUser.user_id == user_id)
        .first()
        is not None
    )


def _ensure_access(db: Session, principal: Principal, user_id: str) -> None:
    if principal.type == "user":
        if principal.id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        return
    # admin
    if not _admin_can_access_user(db, principal.id, user_id):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/applications/exists")
def exists_application(
    user_id: str,
    url: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    _ensure_access(db, principal, user_id)
    row = (
        db.query(Application)
        .filter(Application.user_id == user_id, Application.url == url)
        .order_by(Application.created_at.desc())
        .first()
    )
    if not row:
        return {"exists": False}
    return {
        "exists": True,
        "application": {
            "id": row.id,
            "user_id": row.user_id,
            "created_by": (
                db.get(Admin, row.admin_id).name
                if row.admin_id
                else db.get(User, row.user_id).name
            ),
            "company": row.company,
            "role": row.role,
            "stage": row.stage,
            "url": row.url,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        },
    }


@router.get("/applications/stats")
def applications_stats(
    principal: Principal = Depends(get_principal),
    user_id: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
):

    def _floor_hour(dt: datetime) -> datetime:
        return dt.replace(minute=0, second=0, microsecond=0)

    def _floor_day(dt: datetime) -> datetime:
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    qset = db.query(Application)
    if user_id:
        qset = qset.filter(Application.user_id == user_id)

    # --- stage counts ---
    stage_rows = (
        qset.with_entities(
            func.lower(Application.stage).label("stage"),
            func.count(Application.id).label("cnt"),
        )
        .group_by(func.lower(Application.stage))
        .all()
    )
    stage_counts = {(r.stage or "applied"): int(r.cnt) for r in stage_rows}

    # IMPORTANT: use naive UTC to match Postgres `timestamp without time zone`
    now = datetime.utcnow()

    # --- time bucketing config ---
    if days == 1:
        step = "hour"
        # last 24 hour-buckets including current hour
        start = _floor_hour(now) - timedelta(hours=23)
        cutoff = start
        time_expr = func.date_trunc("hour", Application.created_at)
    else:
        step = "day"
        # last N day-buckets including today (UTC day)
        start = _floor_day(now) - timedelta(days=days - 1)
        cutoff = start
        time_expr = func.date_trunc("day", Application.created_at)

    # --- query grouped counts ---
    rows = (
        qset.filter(Application.created_at >= cutoff)
        .with_entities(
            time_expr.label("t"),
            func.count(Application.id).label("cnt"),
        )
        .group_by(time_expr)
        .order_by(time_expr)
        .all()
    )

    # Keys shown here are datetimes (bucket starts)
    bucket_counts = {r.t: int(r.cnt) for r in rows}

    # --- build series (use datetime keys, format only for output) ---
    series = []
    if step == "hour":
        for i in range(24):
            bucket = start + timedelta(hours=i)  # naive datetime key
            series.append(
                {
                    "time": bucket.strftime("%Y-%m-%d %H:00"),
                    "count": bucket_counts.get(bucket, 0),
                }
            )
    else:
        for i in range(days):
            bucket = start + timedelta(days=i)  # naive datetime key
            series.append(
                {
                    "day": bucket.date().isoformat(),
                    "count": bucket_counts.get(bucket, 0),
                }
            )

    # --- rates and totals ---
    total = int(sum(stage_counts.values()))
    interviews = int(stage_counts.get("interview", 0))
    offers = int(stage_counts.get("offer", 0))
    rejected = int(stage_counts.get("rejected", 0))
    applied = int(stage_counts.get("applied", 0))

    return {
        "total": total,
        "stage_counts": stage_counts,
        "series": series,  # hourly OR daily
        "series_unit": step,  # "hour" | "day"
        "success_rate": offers / max(1, total),
        "interview_rate": interviews / max(1, total),
        "rejection_rate": rejected / max(1, total),
        "applied_count": applied,
        "interview_count": interviews,
        "offer_count": offers,
        "rejected_count": rejected,
    }


@router.get("/applications")
def list_applications(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    view_mode: str = Query("kanban", regex="^(kanban|paged)$"),
    stage: Optional[str] = None,
    user_id: Optional[str] = None,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    query = db.query(Application)

    if principal.type == "user":
        query = query.filter(Application.user_id == principal.id)
    else:
        # admin sees all users they have, optionally scoped to one user
        query = query.join(AdminUser, AdminUser.user_id == Application.user_id).filter(
            AdminUser.admin_id == principal.id
        )
        if user_id and user_id != "__all__":
            query = query.filter(Application.user_id == user_id)

    if stage:
        query = query.filter(Application.stage == stage)

    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            or_(
                Application.company.ilike(like),
                Application.role.ilike(like),
                Application.stage.ilike(like),
                Application.url.ilike(like),
                Application.source_site.ilike(like),
            )
        )

    total = query.count()
    print(f"Total applications found: {total}")
    items = (
        query.order_by(Application.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    def to_dict(a: Application):
        return {
            "id": a.id,
            "user_id": a.user_id,
            "admin_id": a.admin_id,
            "company": a.company,
            "role": a.role,
            "stage": a.stage,
            "url": a.url,
            "source_site": a.source_site,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }

    return {
        "items": [to_dict(a) for a in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get(
    "/applications/{app_id}",
    response_model=ApplicationOut,
)
def get_application(app_id: int, db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "Application not found")
    return a


@router.patch(
    "/applications/{app_id}",
    response_model=ApplicationOut,
)
def update_application(
    app_id: str, payload: ApplicationUpdateIn, db: Session = Depends(get_db)
):
    print(f"Updating application {app_id} to stage {payload.stage}")
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "Application not found")
    a.stage = payload.stage
    db.commit()
    db.refresh(a)
    return a
