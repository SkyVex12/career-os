from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import User
from ..auth import get_principal, Principal

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/me")
def me(principal: Principal = Depends(get_principal)):
    return principal

@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    if principal["type"] == "user":
        u = db.query(User).filter(User.id == principal["user_id"]).first()
        return {"items": [{"id": u.id, "name": u.name}]} if u else {"items":[]}

    # admin
    print(principal)
    users = db.query(User).filter(User.admin_id == principal["admin_id"]).order_by(User.id.asc()).all()
    return {"items": [{"id": u.id, "name": u.name} for u in users]}
