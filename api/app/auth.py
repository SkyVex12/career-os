import os
from typing import Literal, TypedDict, Optional
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import AuthToken, User

class Principal(TypedDict, total=False):
    type: Literal["admin","user"]
    admin_id: str
    user_id: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_principal(
    db: Session = Depends(get_db),
    x_auth_token: str = Header(default=""),
    x_extension_token: str = Header(default=""),
) -> Principal:
    # Dev convenience: AUTH_DISABLED=1 -> act as admin a1
    if os.getenv("AUTH_DISABLED","").strip() == "1":
        return {"type":"admin","admin_id":"a1"}

    token = (x_auth_token or x_extension_token or "").strip()
    if not token:
        raise HTTPException(401, "Missing auth token")

    row = db.query(AuthToken).filter(AuthToken.token == token).first()
    if not row:
        raise HTTPException(401, "Invalid auth token")

    if row.principal_type == "admin":
        return {"type":"admin","admin_id":row.principal_id}
    if row.principal_type == "user":
        # ensure user exists
        u = db.query(User).filter(User.id == row.principal_id).first()
        if not u:
            raise HTTPException(401, "User for token not found")
        return {"type":"user","user_id":u.id}
    raise HTTPException(401, "Invalid principal type")

def assert_user_access(principal: Principal, user_id: str, db: Session) -> None:
    if principal["type"] == "user":
        if principal["user_id"] != user_id:
            raise HTTPException(403, "Forbidden for this user_id")
        return
    # admin: check user belongs to admin
    u = db.query(User).filter(User.id == user_id).first()
    if not u or u.admin_id != principal["admin_id"]:
        raise HTTPException(403, "Forbidden for this user_id")
