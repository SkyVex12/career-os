from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..auth import Principal, get_db, get_principal
from ..models import Application, AdminUser, Admin, User


router = APIRouter(prefix="/v1", tags=["applications"])


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


@router.get("/applications")
def list_applications(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
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

    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            or_(
                Application.company.ilike(like),
                Application.role.ilike(like),
                Application.stage.ilike(like),
                Application.url.ilike(like),
            )
        )

    total = query.count()
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
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }

    return {
        "items": [to_dict(a) for a in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }
