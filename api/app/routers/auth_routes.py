from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from ..auth import Principal, get_db, get_principal, mint_token
from ..models import Admin, AdminUser, AuthCredential, AuthToken, User
from ..security import hash_password, verify_password

router = APIRouter(prefix="/v1", tags=["auth"])


class MeOut(BaseModel):
    type: str
    admin_id: str | None = None
    user_id: str | None = None
    name: str | None = None


@router.get("/me", response_model=MeOut)
def me(principal: Principal = Depends(get_principal)) -> MeOut:
    if principal.type == "admin":
        return MeOut(type="admin", admin_id=principal.id, name=principal.name)
    return MeOut(type="user", user_id=principal.id, name=principal.name)


@router.get("/admins/public")
def list_admins_public(db: Session = Depends(get_db)):
    items = db.query(Admin).order_by(Admin.created_at.desc()).all()
    return {"items": [{"id": a.id, "name": a.name} for a in items]}


class SignupIn(BaseModel):
    role: str = Field(pattern="^(user|admin)$")
    email: EmailStr
    password: str = Field(min_length=6)
    firstname: str | None = None
    lastname: str | None = None
    dob: str | None = None

    # If role == user, you can link to multiple admins
    admin_ids: list[str] | None = None
    # Backward-compat single selection
    admin_id: str | None = None


@router.post("/auth/signup")
def signup(payload: SignupIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    exists = db.query(AuthCredential).filter(AuthCredential.email == email).first()
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")

    now = dt.datetime.utcnow()
    full_name = f"{payload.firstname or ''} {payload.lastname or ''}".strip() or None
    if payload.role == "admin":
        admin_id = f"a{now.strftime('%Y%m%d%H%M%S')}{now.microsecond}"
        admin = Admin(
            id=admin_id,
            name=full_name or "Admin",
            first_name=payload.firstname,
            last_name=payload.lastname,
            created_at=now,
            updated_at=now,
        )
        db.add(admin)

        db.add(
            AuthCredential(
                email=email,
                password_hash=hash_password(payload.password),
                principal_type="admin",
                principal_id=admin_id,
                created_at=now,
            )
        )
        token = mint_token(db, "admin", admin_id, full_name)
        db.commit()
        return {
            "token": token,
            "principal": {"type": "admin", "admin_id": admin_id, "name": full_name},
        }

    # role user
    user_id = f"u{now.strftime('%Y%m%d%H%M%S')}{now.microsecond}"
    user = User(
        id=user_id,
        name=full_name or None,
        first_name=payload.firstname,
        last_name=payload.lastname,
        dob=payload.dob,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.add(
        AuthCredential(
            email=email,
            password_hash=hash_password(payload.password),
            principal_type="user",
            principal_id=user_id,
            created_at=now,
        )
    )

    admin_ids = set(payload.admin_ids or [])
    if payload.admin_id:
        admin_ids.add(payload.admin_id)

    # validate admins exist (optional strict)
    if admin_ids:
        existing_admin_ids = {
            a.id for a in db.query(Admin).filter(Admin.id.in_(list(admin_ids))).all()
        }
        missing = sorted(list(admin_ids - existing_admin_ids))
        if missing:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Some admins not found",
                    "missing_admin_ids": missing,
                },
            )

        for aid in existing_admin_ids:
            db.add(AdminUser(admin_id=aid, user_id=user_id, created_at=now))

    token = mint_token(db, "user", user_id, full_name)
    db.commit()
    return {
        "token": token,
        "principal": {"type": "user", "user_id": user_id, "name": full_name},
    }


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/auth/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    cred = db.query(AuthCredential).filter(AuthCredential.email == email).first()
    if not cred or not verify_password(payload.password, cred.password_hash):
        print(
            verify_password(payload.password, cred.password_hash) if cred else "no cred"
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = mint_token(db, cred.principal_type, cred.principal_id, cred.principal_name)
    db.commit()
    if cred.principal_type == "admin":
        return {
            "token": token,
            "principal": {
                "type": "admin",
                "admin_id": cred.principal_id,
                "name": cred.principal_name,
            },
        }
    return {
        "token": token,
        "principal": {
            "type": "user",
            "user_id": cred.principal_id,
            "name": cred.principal_name,
        },
    }


@router.post("/auth/logout")
def logout(
    db: Session = Depends(get_db),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
):
    if not x_auth_token:
        return {"ok": True}
    db.query(AuthToken).filter(AuthToken.token == x_auth_token.strip()).delete()
    db.commit()
    return {"ok": True}
