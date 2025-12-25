from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from ..db import SessionLocal
from ..models import Application, User
from ..auth import get_principal, Principal, assert_user_access

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _scoped_query(db: Session, principal: Principal):
    q = db.query(Application)
    if principal["type"] == "user":
        q = q.filter(Application.user_id == principal["user_id"])
    else:
        # admin: restrict to users under admin
        user_ids = [u.id for u in db.query(User.id).filter(User.admin_id == principal["admin_id"]).all()]
        q = q.filter(Application.user_id.in_(user_ids)) if user_ids else q.filter(Application.user_id == "__none__")
    return q

@router.get("/applications")
def list_applications(
    principal: Principal = Depends(get_principal),
    user_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    qset = _scoped_query(db, principal)

    if user_id:
        assert_user_access(principal, user_id, db)
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

    total = qset.count()
    items = (
        qset.order_by(Application.created_at.desc())
        .offset((page-1)*limit)
        .limit(limit)
        .all()
    )

    return {
        "items": [
            {
                "id": a.id,
                "user_id": a.user_id,
                "company": a.company,
                "role": a.role,
                "url": a.url,
                "stage": a.stage,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in items
        ],
        "page": page,
        "limit": limit,
        "total": total,
        "pages": (total + limit - 1)//limit,
    }

@router.get("/applications/exists")
def application_exists(
    principal: Principal = Depends(get_principal),
    user_id: str = Query(...),
    url: str = Query(...),
    db: Session = Depends(get_db),
):
    assert_user_access(principal, user_id, db)
    a = db.query(Application).filter(Application.user_id == user_id, Application.url == url).first()
    return {"exists": bool(a), "application": {
        "id": a.id,
        "user_id": a.user_id,
        "company": a.company,
        "role": a.role,
        "url": a.url,
        "stage": a.stage,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } if a else None}

@router.get("/applications/stats")
def applications_stats(
    principal: Principal = Depends(get_principal),
    user_id: str | None = Query(default=None),
    days: int = Query(default=30, ge=7, le=365),
    db: Session = Depends(get_db),
):
    qset = _scoped_query(db, principal)
    if user_id:
        assert_user_access(principal, user_id, db)
        qset = qset.filter(Application.user_id == user_id)

    stage_rows = (
        qset.with_entities(func.lower(Application.stage).label("stage"), func.count(Application.id))
        .group_by(func.lower(Application.stage))
        .all()
    )
    stage_counts = {(r[0] or "applied"): int(r[1]) for r in stage_rows}

    cutoff = datetime.utcnow() - timedelta(days=days-1)
    day_rows = (
        qset.filter(Application.created_at >= cutoff)
        .with_entities(func.strftime("%Y-%m-%d", Application.created_at).label("day"), func.count(Application.id))
        .group_by(func.strftime("%Y-%m-%d", Application.created_at))
        .order_by(func.strftime("%Y-%m-%d", Application.created_at))
        .all()
    )
    day_map = {r[0]: int(r[1]) for r in day_rows}

    series = []
    for i in range(days):
        d = (cutoff + timedelta(days=i)).date().isoformat()
        series.append({"day": d, "count": day_map.get(d, 0)})

    applied = stage_counts.get("applied", 0) + stage_counts.get("no", 0)
    interview = stage_counts.get("interview", 0) + stage_counts.get("yes", 0)
    rejected = stage_counts.get("rejected", 0) + stage_counts.get("reject", 0)

    total = sum(stage_counts.values())
    success_rate = (interview / total) if total else 0.0

    return {"stage_counts": stage_counts, "series": series, "success_rate": success_rate, "total": total}


@router.get("/applications/exists-any")
def application_exists_any(
    principal: Principal = Depends(get_principal),
    url: str = Query(...),
    db: Session = Depends(get_db),
):
    qset = _scoped_query(db, principal).filter(Application.url == url)
    matches = qset.order_by(Application.created_at.desc()).limit(20).all()
    return {
        "exists": bool(matches),
        "count": len(matches),
        "applications": [
            {
                "id": a.id,
                "user_id": a.user_id,
                "company": a.company,
                "role": a.role,
                "url": a.url,
                "stage": a.stage,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in matches
        ],
    }
