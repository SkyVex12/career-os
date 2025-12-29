from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime

from ..db import SessionLocal
from ..models import User, BaseResume
from ..auth import get_principal, Principal

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class BaseResumeIn(BaseModel):
    content_text: str = Field(..., min_length=20)


@router.put("/users/{user_id}/base-resume")
def put_base_resume(
    user_id: str,
    payload: BaseResumeIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):

    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        u = User(id=user_id, admin_id=principal.get("admin_id"))
        db.add(u)
        db.commit()

    br = db.get(BaseResume, user_id)
    now = datetime.utcnow()
    if br:
        br.content_text = payload.content_text
        br.updated_at = now
    else:
        br = BaseResume(
            user_id=user_id, content_text=payload.content_text, updated_at=now
        )
        db.add(br)
    db.commit()
    return {"ok": True, "user_id": user_id, "updated_at": now.isoformat()}


@router.get("/users/{user_id}/base-resume")
def get_base_resume(
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    br = db.get(BaseResume, user_id)
    if not br:
        raise HTTPException(404, "Base resume not found")
    return {
        "user_id": user_id,
        "content_text": br.content_text,
        "updated_at": br.updated_at.isoformat(),
    }
