from __future__ import annotations

import datetime as dt
import os
import re
from typing import Optional, Any

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from ..auth import Principal, get_db, get_principal
from ..models import OutlookIntegration, EmailEvent, Application, ApplicationUpdateSuggestion, AdminUser


router = APIRouter(prefix="/v1/integrations/outlook", tags=["outlook"])


# ----------------- auth + scope helpers -----------------

def _can_access_user(db: Session, principal: Principal, user_id: str) -> bool:
    if principal.type == "user":
        return principal.id == user_id
    # admin -> must be linked
    link = db.query(AdminUser).filter(AdminUser.admin_id == principal.id, AdminUser.user_id == user_id).first()
    return link is not None


def _now_utc() -> dt.datetime:
    return dt.datetime.utcnow().replace(tzinfo=None)


# ----------------- graph helpers -----------------

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

def canonicalize_url(input_url: str) -> str:
    """Basic canonicalization: strip hash, sort query params, trim trailing slash."""
    try:
        from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
        u = urlparse(input_url)
        q = urlencode(sorted(parse_qsl(u.query, keep_blank_values=True)))
        u2 = u._replace(fragment="", query=q)
        s = urlunparse(u2)
        if s.endswith("/"):
            s = s[:-1]
        return s
    except Exception:
        s = (input_url or "").split("#")[0]
        return s[:-1] if s.endswith("/") else s


def _token_valid(row: OutlookIntegration) -> bool:
    if not row or not row.access_token:
        return False
    if not row.expires_at:
        return True
    return row.expires_at > _now_utc() + dt.timedelta(seconds=30)


def _refresh_access_token(row: OutlookIntegration) -> None:
    """Refresh access token using refresh_token.
    Requires env:
      OUTLOOK_TENANT_ID (or 'common')
      OUTLOOK_CLIENT_ID
      OUTLOOK_CLIENT_SECRET
    """
    if not row.refresh_token:
        raise HTTPException(status_code=400, detail="Missing refresh_token for Outlook integration")

    tenant = os.getenv("OUTLOOK_TENANT_ID", "common")
    client_id = os.getenv("OUTLOOK_CLIENT_ID")
    client_secret = os.getenv("OUTLOOK_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Outlook client env not configured (OUTLOOK_CLIENT_ID/SECRET)")

    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": row.refresh_token,
        "scope": "https://graph.microsoft.com/.default offline_access",
    }
    resp = requests.post(token_url, data=data, timeout=30)
    if resp.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Token refresh failed: {resp.status_code} {resp.text[:300]}")
    j = resp.json()
    row.access_token = j.get("access_token")
    if j.get("refresh_token"):
        row.refresh_token = j.get("refresh_token")
    expires_in = int(j.get("expires_in", 3600))
    row.expires_at = _now_utc() + dt.timedelta(seconds=expires_in)
    row.updated_at = _now_utc()


def _graph_get(access_token: str, path: str, params: dict[str, Any] | None = None) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
    resp = requests.get(url, headers=headers, params=params or {}, timeout=30)
    if resp.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Graph API error: {resp.status_code} {resp.text[:300]}")
    return resp.json()


def _classify_email(subject: str, preview: str) -> tuple[str, int, str]:
    text = f"{subject or ''} {preview or ''}".lower()
    # strongest signals first
    if re.search(r"\b(offer|congratulations|we are pleased to)\b", text):
        return "offer", 92, "Offer keywords in subject/body"
    if re.search(r"\b(unfortunately|not selected|regret to inform|we will not be moving forward|rejected)\b", text):
        return "rejected", 90, "Rejection keywords in subject/body"
    if re.search(r"\b(interview|schedule|calendar|availability|phone screen|onsite|meet with)\b", text):
        return "interview", 85, "Interview scheduling keywords in subject/body"
    if re.search(r"\b(application received|thanks for applying|thank you for applying|we received your application)\b", text):
        return "applied", 70, "Application receipt keywords"
    # default: unknown, do not update
    return "unknown", 0, "No strong status keywords"


def _match_application(db: Session, user_id: str, subject: str, preview: str) -> tuple[Optional[str], int, str]:
    """Return (application_id, confidence, reason)."""
    text = f"{subject or ''} {preview or ''}".lower()
    # Try to match by company name (exact-ish) among recent applications
    apps = (
        db.query(Application)
        .filter(Application.user_id == user_id)
        .order_by(Application.updated_at.desc())
        .limit(100)
        .all()
    )

    # Match by URL domain in text (e.g., greenhouse/lever/workday links)
    for app in apps:
        try:
            u = canonicalize_url(app.url)
            m = re.search(r"https?://([^/]+)/", u)
            dom = m.group(1).lower() if m else ""
            if dom and dom in text:
                return app.id, 92, f"Matched application by URL domain: {dom}"
        except Exception:
            pass

    # Match by company name presence
    for app in apps:
        c = (app.company or "").lower().strip()
        if c and len(c) >= 3 and c in text:
            return app.id, 75, f"Matched application by company name: {app.company}"

    return None, 0, "No confident application match"


# ----------------- endpoints -----------------

class OutlookConnectIn(BaseModel):
    user_id: str
    account_email: Optional[EmailStr] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = Field(default=3600, ge=60, le=86400)
    auto_update: bool = False


@router.post("/connect")
def connect_outlook(payload: OutlookConnectIn, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    """MVP helper to save Outlook tokens/settings for a user.
    In production, replace with OAuth callback flow.
    """
    if not _can_access_user(db, principal, payload.user_id):
        raise HTTPException(status_code=403, detail="Not allowed")

    row = db.query(OutlookIntegration).filter(OutlookIntegration.user_id == payload.user_id).first()
    now = _now_utc()
    if not row:
        row = OutlookIntegration(user_id=payload.user_id, created_at=now, updated_at=now)
        db.add(row)

    row.account_email = str(payload.account_email) if payload.account_email else row.account_email
    row.access_token = payload.access_token or row.access_token
    row.refresh_token = payload.refresh_token or row.refresh_token
    row.expires_at = now + dt.timedelta(seconds=int(payload.expires_in or 3600)) if (payload.access_token or row.access_token) else row.expires_at
    row.auto_update = 1 if payload.auto_update else 0
    row.updated_at = now
    db.commit()
    return {"ok": True}


class OutlookSyncOut(BaseModel):
    ok: bool
    fetched: int
    new_events: int
    new_suggestions: int
    last_sync_at: Optional[dt.datetime] = None


@router.post("/sync", response_model=OutlookSyncOut)
def sync_outlook(
    user_id: str,
    lookback_minutes: int = 60,
    max_messages: int = 25,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """Poll inbox for recent messages and create update suggestions (approve-first).
    - Uses last_sync_at if present; otherwise uses lookback_minutes window.
    """
    if not _can_access_user(db, principal, user_id):
        raise HTTPException(status_code=403, detail="Not allowed")

    integ = db.query(OutlookIntegration).filter(OutlookIntegration.user_id == user_id).first()
    if not integ:
        raise HTTPException(status_code=400, detail="Outlook integration not connected")

    # ensure token
    if not _token_valid(integ):
        _refresh_access_token(integ)
        db.commit()

    since = integ.last_sync_at or (_now_utc() - dt.timedelta(minutes=int(lookback_minutes)))
    # Graph supports $filter=receivedDateTime ge ...
    # Use ISO 8601 with Z
    since_iso = since.replace(microsecond=0).isoformat() + "Z"

    params = {
        "$top": str(max_messages),
        "$select": "id,subject,from,receivedDateTime,bodyPreview,internetMessageId,webLink",
        "$orderby": "receivedDateTime desc",
        "$filter": f"receivedDateTime ge {since_iso}",
    }
    data = _graph_get(integ.access_token, "/me/mailFolders/Inbox/messages", params=params)
    items = data.get("value") or []
    fetched = len(items)

    new_events = 0
    new_suggestions = 0

    for msg in items:
        internet_id = msg.get("internetMessageId")
        # Dedup: if internet_message_id missing, fallback to message_id (less ideal)
        dedupe_id = internet_id or msg.get("id")
        # skip if already ingested
        existing = (
            db.query(EmailEvent)
            .filter(EmailEvent.user_id == user_id, EmailEvent.provider == "outlook", EmailEvent.internet_message_id == dedupe_id)
            .first()
        )
        if existing:
            continue

        from_email = None
        try:
            from_email = msg.get("from", {}).get("emailAddress", {}).get("address")
        except Exception:
            from_email = None

        received = None
        try:
            received = dt.datetime.fromisoformat(msg.get("receivedDateTime").replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            received = None

        ev = EmailEvent(
            user_id=user_id,
            provider="outlook",
            message_id=msg.get("id") or "",
            internet_message_id=dedupe_id,
            from_email=from_email,
            subject=msg.get("subject"),
            received_at=received,
            body_preview=msg.get("bodyPreview"),
            web_link=msg.get("webLink"),
            raw_json=None,
            created_at=_now_utc(),
        )
        db.add(ev)
        db.flush()  # so ev.id exists
        new_events += 1

        stage, stage_conf, stage_reason = _classify_email(ev.subject or "", ev.body_preview or "")
        if stage == "unknown":
            continue

        app_id, app_conf, app_reason = _match_application(db, user_id, ev.subject or "", ev.body_preview or "")
        conf = min(100, int(0.6 * stage_conf + 0.4 * app_conf))

        if app_id is None or conf < 60:
            # still create suggestion but without application_id (user can manually pick later)
            sugg = ApplicationUpdateSuggestion(
                user_id=user_id,
                application_id=app_id,
                email_event_id=ev.id,
                suggested_stage=stage,
                confidence=conf,
                reason=f"{stage_reason}; {app_reason}",
                status="pending",
                created_at=_now_utc(),
                updated_at=_now_utc(),
            )
            db.add(sugg)
            new_suggestions += 1
            continue

        sugg = ApplicationUpdateSuggestion(
            user_id=user_id,
            application_id=app_id,
            email_event_id=ev.id,
            suggested_stage=stage,
            confidence=conf,
            reason=f"{stage_reason}; {app_reason}",
            status="pending",
            created_at=_now_utc(),
            updated_at=_now_utc(),
        )
        db.add(sugg)
        new_suggestions += 1

    integ.last_sync_at = _now_utc()
    integ.updated_at = _now_utc()
    db.commit()

    return OutlookSyncOut(ok=True, fetched=fetched, new_events=new_events, new_suggestions=new_suggestions, last_sync_at=integ.last_sync_at)
