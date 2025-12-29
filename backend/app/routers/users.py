from __future__ import annotations

import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from sqlalchemy.orm import Session

from ..auth import Principal, get_db, get_principal, require_admin
from ..models import AdminUser, User, AuthCredential
from ..security import hash_password


router = APIRouter(prefix="/v1", tags=["users"])


class UserOut(BaseModel):
    id: str
    email: Optional[str] = None
    name: Optional[str] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    dob: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    if principal.type == "admin":
        rows = (
            db.query(User)
            .join(AdminUser, AdminUser.user_id == User.id)
            .filter(AdminUser.admin_id == principal.id)
            .order_by(User.created_at.desc())
            .all()
        )
        return {"items": [UserOut.model_validate(u).model_dump() for u in rows]}
    else:
        u = db.query(User).filter(User.id == principal.id).first()
        if not u:
            return {"items": []}
        return {"items": [UserOut.model_validate(u).model_dump()]}


class AdminCreateUserIn(BaseModel):
    email: EmailStr
    password: str
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    dob: Optional[str] = None
    # optionally link to additional admins too (besides the creator)
    admin_ids: Optional[List[str]] = None


@router.post("/admin/users")
def admin_create_user_and_link(
    payload: AdminCreateUserIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    require_admin(principal)

    # email unique constraint in AuthCredential
    existing = (
        db.query(AuthCredential)
        .filter(AuthCredential.email == payload.email.lower())
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    now = dt.datetime.utcnow()
    user_id = f"u{now.strftime('%Y%m%d%H%M%S')}{now.microsecond}"

    user = User(
        id=user_id,
        name=f"{payload.firstname or ''} {payload.lastname or ''}".strip() or None,
        first_name=payload.firstname,
        last_name=payload.lastname,
        dob=payload.dob,
        created_at=now,
        updated_at=now,
    )
    db.add(user)

    cred = AuthCredential(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        principal_type="user",
        principal_id=user_id,
        principal_name=user.first_name + " " + user.last_name,
        created_at=now,
    )
    db.add(cred)

    # link to creator admin + any others
    admin_ids = set(payload.admin_ids or [])
    admin_ids.add(principal.id)
    for aid in admin_ids:
        db.add(AdminUser(admin_id=aid, user_id=user_id, created_at=now))

    db.commit()
    return {"user": UserOut.model_validate(user).model_dump()}


from ..models import BaseResume


class BaseResumeIn(BaseModel):
    content_text: str = Field(..., min_length=20)


@router.put("/users/{user_id}/base-resume")
def put_base_resume(
    user_id: str,
    payload: BaseResumeIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    # access: user self or admin linked
    if principal.type == "user":
        if principal.id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
    else:
        if (
            db.query(AdminUser)
            .filter(AdminUser.admin_id == principal.id, AdminUser.user_id == user_id)
            .first()
            is None
        ):
            raise HTTPException(status_code=403, detail="Forbidden")

    now = dt.datetime.utcnow()
    row = db.get(BaseResume, user_id)
    if row:
        row.content_text = payload.content_text
        row.updated_at = now
    else:
        row = BaseResume(
            user_id=user_id,
            content_text=payload.content_text,
            created_at=now,
            updated_at=now,
        )
        db.add(row)

    db.commit()
    return {"ok": True, "user_id": user_id, "updated_at": now.isoformat()}


@router.get("/users/{user_id}/base-resume")
def get_base_resume(
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    if principal.type == "user":
        if principal.id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
    else:
        if (
            db.query(AdminUser)
            .filter(AdminUser.admin_id == principal.id, AdminUser.user_id == user_id)
            .first()
            is None
        ):
            raise HTTPException(status_code=403, detail="Forbidden")

    br = db.get(BaseResume, user_id)
    return {
        "user_id": user_id,
        "content_text": br.content_text if br else "",
        "updated_at": br.updated_at.isoformat() if br else None,
    }


class BaseResumeListItem(BaseModel):
    user_id: str
    title: str | None = None
    content_text: str = ""
    updated_at: str | None = None


@router.get("/base-resumes")
def list_base_resumes(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """List base resumes visible to the current principal.

    - Admin: all linked users (+ their base resume content, if any)
    - User: only themselves
    """
    if principal.type == "admin":
        rows = (
            db.query(User, BaseResume)
            .join(AdminUser, AdminUser.user_id == User.id)
            .outerjoin(BaseResume, BaseResume.user_id == User.id)
            .filter(AdminUser.admin_id == principal.id)
            .order_by(User.created_at.desc())
            .all()
        )
        items = []
        for u, br in rows:
            items.append(
                {
                    "user_id": u.id,
                    "title": u.name or u.id,
                    "content_text": br.content_text if br else "",
                    "updated_at": br.updated_at.isoformat() if br else None,
                }
            )
        return {"items": items}
    else:
        u = db.query(User).filter(User.id == principal.id).first()
        br = db.get(BaseResume, principal.id)
        return {
            "items": [
                {
                    "user_id": principal.id,
                    "title": (u.name if u else None) or principal.id,
                    "content_text": br.content_text if br else "",
                    "updated_at": br.updated_at.isoformat() if br else None,
                }
            ]
        }


class LinkUserIn(BaseModel):
    user_id: str


@router.get("/admin/users/all")
def admin_list_all_users(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    require_admin(principal)
    rows = db.query(User).order_by(User.created_at.desc()).all()
    return {"items": [UserOut.model_validate(u).model_dump() for u in rows]}


@router.post("/admin/users/link")
def admin_link_user(
    payload: LinkUserIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    require_admin(principal)

    # verify user exists
    u = db.query(User).filter(User.id == payload.user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    now = dt.datetime.utcnow()
    existing = (
        db.query(AdminUser)
        .filter(
            AdminUser.admin_id == principal.id, AdminUser.user_id == payload.user_id
        )
        .first()
    )
    if existing:
        return {"ok": True}

    db.add(AdminUser(admin_id=principal.id, user_id=payload.user_id, created_at=now))
    db.commit()
    return {"ok": True}


@router.post("/admin/users/unlink")
def admin_unlink_user(
    payload: LinkUserIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    require_admin(principal)

    row = (
        db.query(AdminUser)
        .filter(
            AdminUser.admin_id == principal.id, AdminUser.user_id == payload.user_id
        )
        .first()
    )
    if row is None:
        return {"ok": True}

    db.delete(row)
    db.commit()
    return {"ok": True}
