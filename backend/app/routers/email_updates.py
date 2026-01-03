from __future__ import annotations

import datetime as dt
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import Principal, get_db, get_principal
from ..models import ApplicationUpdateSuggestion, EmailEvent, Application, AdminUser

router = APIRouter(prefix="/v1/email", tags=["email-updates"])


def _can_access_user(db: Session, principal: Principal, user_id: str) -> bool:
    if principal.type == "user":
        return principal.id == user_id
    link = db.query(AdminUser).filter(AdminUser.admin_id == principal.id, AdminUser.user_id == user_id).first()
    return link is not None


class SuggestionOut(BaseModel):
    id: int
    application_id: Optional[str]
    suggested_stage: str
    confidence: int
    reason: Optional[str]
    status: str
    created_at: dt.datetime
    email: dict

    class Config:
        from_attributes = True


@router.get("/suggestions", response_model=List[SuggestionOut])
def list_suggestions(
    user_id: str,
    status: str = "pending",
    limit: int = 50,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    if not _can_access_user(db, principal, user_id):
        raise HTTPException(status_code=403, detail="Not allowed")

    q = (
        db.query(ApplicationUpdateSuggestion, EmailEvent)
        .join(EmailEvent, EmailEvent.id == ApplicationUpdateSuggestion.email_event_id)
        .filter(ApplicationUpdateSuggestion.user_id == user_id)
    )
    if status:
        q = q.filter(ApplicationUpdateSuggestion.status == status)
    rows = q.order_by(ApplicationUpdateSuggestion.created_at.desc()).limit(limit).all()

    out = []
    for sugg, ev in rows:
        out.append(
            SuggestionOut(
                id=sugg.id,
                application_id=sugg.application_id,
                suggested_stage=sugg.suggested_stage,
                confidence=int(sugg.confidence or 0),
                reason=sugg.reason,
                status=sugg.status,
                created_at=sugg.created_at,
                email={
                    "from": ev.from_email,
                    "subject": ev.subject,
                    "received_at": ev.received_at,
                    "preview": ev.body_preview,
                    "web_link": ev.web_link,
                },
            )
        )
    return out


class ApproveIn(BaseModel):
    # allow overriding application_id in approve step (useful when match was weak)
    application_id: Optional[str] = None
    stage: Optional[str] = None


@router.post("/suggestions/{suggestion_id}/approve")
def approve_suggestion(
    suggestion_id: int,
    payload: ApproveIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    sugg = db.query(ApplicationUpdateSuggestion).filter(ApplicationUpdateSuggestion.id == suggestion_id).first()
    if not sugg:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    if not _can_access_user(db, principal, sugg.user_id):
        raise HTTPException(status_code=403, detail="Not allowed")

    app_id = payload.application_id or sugg.application_id
    stage = payload.stage or sugg.suggested_stage

    if not app_id:
        raise HTTPException(status_code=400, detail="application_id required to approve this suggestion")

    app = db.query(Application).filter(Application.id == app_id, Application.user_id == sugg.user_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    app.stage = stage
    app.updated_at = dt.datetime.utcnow()

    sugg.status = "applied"
    sugg.application_id = app_id
    sugg.updated_at = dt.datetime.utcnow()

    db.commit()
    return {"ok": True, "application_id": app.id, "stage": app.stage}


@router.post("/suggestions/{suggestion_id}/reject")
def reject_suggestion(
    suggestion_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    sugg = db.query(ApplicationUpdateSuggestion).filter(ApplicationUpdateSuggestion.id == suggestion_id).first()
    if not sugg:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    if not _can_access_user(db, principal, sugg.user_id):
        raise HTTPException(status_code=403, detail="Not allowed")

    sugg.status = "rejected"
    sugg.updated_at = dt.datetime.utcnow()
    db.commit()
    return {"ok": True}
