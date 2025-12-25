from fastapi import APIRouter, Depends
from app.db import SessionLocal
from sqlalchemy.orm import Session
from ..models import User

router = APIRouter(prefix="/v1", tags=["users"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    # Return all users. UI expects items:[{id,name?}]
    users = db.query(User).order_by(User.id.asc()).all()
    return {"items": [{"id": u.id, "name": None} for u in users]}
