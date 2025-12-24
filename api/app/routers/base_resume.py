from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime

from app.db import SessionLocal
from app.models import User, BaseResume
from app.auth import require_extension_token

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class BaseResumeIn(BaseModel):
    content_text: str = Field(..., min_length=50)

@router.put("/users/{user_id}/base-resume", dependencies=[Depends(require_extension_token)])
def upsert_base_resume(user_id: str, payload: BaseResumeIn, db: Session = Depends(get_db)):
    # ensure user exists
    if not db.get(User, user_id):
        db.add(User(id=user_id))
        db.commit()

    br = db.get(BaseResume, user_id)
    now = datetime.utcnow()
    if br:
        br.content_text = payload.content_text
        br.updated_at = now
    else:
        br = BaseResume(user_id=user_id, content_text=payload.content_text, updated_at=now)
        db.add(br)
    db.commit()
    return {"ok": True, "user_id": user_id, "updated_at": now.isoformat()}

@router.get("/users/{user_id}/base-resume", dependencies=[Depends(require_extension_token)])
def get_base_resume(user_id: str, db: Session = Depends(get_db)):
    br = db.get(BaseResume, user_id)
    if not br:
        raise HTTPException(404, "Base resume not found")
    return {"user_id": user_id, "content_text": br.content_text, "updated_at": br.updated_at.isoformat()}
