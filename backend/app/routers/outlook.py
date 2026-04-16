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
from ..models import (
    OutlookIntegration,
    EmailEvent,
    Application,
    ApplicationUpdateSuggestion,
    AdminUser,
    JobDescription,
)


router = APIRouter(prefix="/v1/integrations/outlook", tags=["outlook"])


# ----------------- auth + scope helpers -----------------


def _can_access_user(db: Session, principal: Principal, user_id: str) -> bool:
    if principal.type == "user":
        return principal.id == user_id
    # admin -> must be linked
    link = (
        db.query(AdminUser)
        .filter(AdminUser.admin_id == principal.id, AdminUser.user_id == user_id)
        .first()
    )
    return link is not None


def _now_utc() -> dt.datetime:
    return dt.datetime.now().replace(tzinfo=None)


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
        raise HTTPException(
            status_code=400, detail="Missing refresh_token for Outlook integration"
        )

    tenant = os.getenv("OUTLOOK_TENANT_ID", "common")
    client_id = os.getenv("OUTLOOK_CLIENT_ID")
    client_secret = os.getenv("OUTLOOK_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Outlook client env not configured (OUTLOOK_CLIENT_ID/SECRET)",
        )

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
        raise HTTPException(
            status_code=400,
            detail=f"Token refresh failed: {resp.status_code} {resp.text[:300]}",
        )
    j = resp.json()
    row.access_token = j.get("access_token")
    if j.get("refresh_token"):
        row.refresh_token = j.get("refresh_token")
    expires_in = int(j.get("expires_in", 3600))
    row.expires_at = _now_utc() + dt.timedelta(seconds=expires_in)
    row.updated_at = _now_utc()


def _graph_get(
    access_token: str, path: str, params: dict[str, Any] | None = None
) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
    resp = requests.get(url, headers=headers, params=params or {}, timeout=30)
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail=f"Graph API error: {resp.status_code} {resp.text[:300]}",
        )
    return resp.json()


def _classify_email(subject: str, preview: str) -> tuple[str, int, str]:
    text = f"{subject or ''} {preview or ''}".lower()
    # strongest signals first
    if re.search(r"\b(offer|congratulations|we are pleased to)\b", text):
        return "offer", 92, "Offer keywords in subject/body"
    if re.search(
        r"\b(unfortunately|not selected|regret to inform|we will not be moving forward|rejected)\b",
        text,
    ):
        return "rejected", 90, "Rejection keywords in subject/body"
    if re.search(
        r"\b(interview|schedule|calendar|availability|phone screen|onsite|meet with)\b",
        text,
    ):
        return "interview", 85, "Interview scheduling keywords in subject/body"
    if re.search(
        r"\b(application received|thanks for applying|thank you for applying|we received your application)\b",
        text,
    ):
        return "applied", 70, "Application receipt keywords"
    # default: unknown, do not update
    return "unknown", 0, "No strong status keywords"


def _match_application(
    db: Session, user_id: str, subject: str, preview: str
) -> tuple[Optional[str], int, str]:
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
def connect_outlook(
    payload: OutlookConnectIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """MVP helper to save Outlook tokens/settings for a user.
    In production, replace with OAuth callback flow.
    """
    if not _can_access_user(db, principal, payload.user_id):
        raise HTTPException(status_code=403, detail="Not allowed")

    row = (
        db.query(OutlookIntegration)
        .filter(OutlookIntegration.user_id == payload.user_id)
        .first()
    )
    now = _now_utc()
    if not row:
        row = OutlookIntegration(
            user_id=payload.user_id, created_at=now, updated_at=now
        )
        db.add(row)

    row.account_email = (
        str(payload.account_email) if payload.account_email else row.account_email
    )
    row.access_token = payload.access_token or row.access_token
    row.refresh_token = payload.refresh_token or row.refresh_token
    row.expires_at = (
        now + dt.timedelta(seconds=int(payload.expires_in or 3600))
        if (payload.access_token or row.access_token)
        else row.expires_at
    )
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

    integ = (
        db.query(OutlookIntegration)
        .filter(OutlookIntegration.user_id == user_id)
        .first()
    )
    if not integ:
        raise HTTPException(status_code=400, detail="Outlook integration not connected")

    # ensure token
    if not _token_valid(integ):
        _refresh_access_token(integ)
        db.commit()

    since = integ.last_sync_at or (
        _now_utc() - dt.timedelta(minutes=int(lookback_minutes))
    )
    # Graph supports $filter=receivedDateTime ge ...
    # Use ISO 8601 with Z
    since_iso = since.replace(microsecond=0).isoformat() + "Z"

    params = {
        "$top": str(max_messages),
        "$select": "id,subject,from,receivedDateTime,bodyPreview,internetMessageId,webLink",
        "$orderby": "receivedDateTime desc",
        "$filter": f"receivedDateTime ge {since_iso}",
    }
    data = _graph_get(
        integ.access_token, "/me/mailFolders/Inbox/messages", params=params
    )
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
            .filter(
                EmailEvent.user_id == user_id,
                EmailEvent.provider == "outlook",
                EmailEvent.internet_message_id == dedupe_id,
            )
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
            received = dt.datetime.fromisoformat(
                msg.get("receivedDateTime").replace("Z", "+00:00")
            ).replace(tzinfo=None)
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

        stage, stage_conf, stage_reason = _classify_email(
            ev.subject or "", ev.body_preview or ""
        )
        if stage == "unknown":
            continue

        app_id, app_conf, app_reason = _match_application(
            db, user_id, ev.subject or "", ev.body_preview or ""
        )
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

    return OutlookSyncOut(
        ok=True,
        fetched=fetched,
        new_events=new_events,
        new_suggestions=new_suggestions,
        last_sync_at=integ.last_sync_at,
    )


# ----------------- demo seeding -----------------

_DEMO_JDS: dict[str, str] = {
    "WealthCounsel": (
        "WealthCounsel is hiring a Software Developer (Virtual, Full-Time) to "
        "join our product engineering group. You will build and maintain the "
        "document-assembly and practice-management software used by estate "
        "planning and business law attorneys across the U.S.\n\n"
        "Responsibilities:\n"
        "- Design and implement features across our Ruby on Rails and React "
        "stack.\n"
        "- Collaborate closely with product, design, and legal SMEs to ship "
        "user-facing functionality.\n"
        "- Write clean, well-tested code and participate in code reviews.\n"
        "- Contribute to architectural decisions as our platform scales.\n\n"
        "Requirements:\n"
        "- 3+ years of professional software engineering experience.\n"
        "- Strong fundamentals in at least one modern web framework.\n"
        "- Comfort working remotely and asynchronously.\n"
        "- Nice to have: experience in legal-tech or regulated SaaS."
    ),
    "Chronograph": (
        "Chronograph builds portfolio intelligence software for the private "
        "capital industry. We are hiring a Software Engineer to join our Data "
        "Platform team.\n\n"
        "You will:\n"
        "- Build and own scalable data ingestion pipelines and internal APIs.\n"
        "- Work with Python, TypeScript, Postgres, and Kafka.\n"
        "- Partner with product and analytics to turn messy LP/GP data into "
        "reliable product surfaces.\n\n"
        "About you:\n"
        "- 4+ years of backend engineering experience.\n"
        "- Familiarity with data modeling and distributed systems.\n"
        "- A bias toward shipping pragmatic, well-tested code."
    ),
    "Fullsteam": (
        "Fullsteam is hiring a Senior Developer (Remote, US) to build and "
        "extend the payment-processing and vertical SaaS products we operate "
        "across more than 75 business units.\n\n"
        "You will:\n"
        "- Architect and deliver .NET / C# services that handle payments and "
        "business operations at scale.\n"
        "- Lead design reviews and mentor less-senior engineers.\n"
        "- Partner with product to translate vertical-specific needs into "
        "durable platform capabilities.\n\n"
        "Requirements:\n"
        "- 6+ years of backend development, ideally in payments, fintech, or "
        "vertical SaaS.\n"
        "- Strong SQL and API design skills.\n"
        "- Experience operating production services (on-call, SLOs)."
    ),
    "Bitsight": (
        "Bitsight is hiring a Full-Stack Software Engineer for the Ratings "
        "Platform team. You'll work on the core systems that power cyber-risk "
        "ratings used by thousands of enterprises.\n\n"
        "Responsibilities:\n"
        "- Build features across our React front-end and Python/Go back-end "
        "services.\n"
        "- Contribute to data modeling and query performance in a large "
        "Postgres environment.\n"
        "- Participate in system design and architectural discussions.\n\n"
        "Qualifications:\n"
        "- 4+ years of full-stack engineering experience.\n"
        "- Solid grounding in REST/GraphQL API design.\n"
        "- Security or risk-analytics domain experience is a plus."
    ),
    "Axios": (
        "Axios is hiring a Software Engineer to work on the newsroom and "
        "subscription products that power our smart-brevity journalism.\n\n"
        "What you'll do:\n"
        "- Build features across Node/TypeScript services and Next.js "
        "front-ends.\n"
        "- Partner with editors and product managers to ship high-visibility "
        "reader-facing experiences.\n"
        "- Contribute to platform work: observability, CI/CD, performance.\n\n"
        "About you:\n"
        "- 3+ years of full-stack experience, ideally at a media or consumer "
        "product company.\n"
        "- Comfort with ambiguity and shipping quickly.\n"
        "- Care about the craft of journalism and the tools that support it."
    ),
    "LTK": (
        "LTK (formerly rewardStyle / LIKEtoKNOW.it) is hiring a Software "
        "Engineer to build the creator-commerce platform that powers more "
        "than 200,000 lifestyle creators and their audiences.\n\n"
        "Responsibilities:\n"
        "- Design and ship features across our Python/Go services and "
        "TypeScript/React applications.\n"
        "- Partner with creator and consumer product teams on high-traffic "
        "shopping experiences.\n"
        "- Contribute to API design, data modeling, and system reliability.\n\n"
        "Requirements:\n"
        "- 3+ years of software engineering experience.\n"
        "- Familiarity with one of our core stacks (Python, Go, or TS/React).\n"
        "- Interest in commerce, creators, or large-scale consumer apps."
    ),
}


_DEMO_EMAILS: list[dict] = [
    {
        "from": "careers@wealthcounsel.com",
        "from_name": "WealthCounsel Talent Team",
        "subject": "Thanks for applying — Software Developer (Virtual, Full-Time) at WealthCounsel",
        "preview": (
            "Hi Timothy,\n\nThanks for applying to the Software Developer (Virtual, Full-Time) "
            "role at WealthCounsel. We've received your application and our hiring team "
            "will be reviewing it over the next 5–7 business days. If your background is "
            "a match for the role, a recruiter will reach out to schedule an introductory "
            "conversation.\n\nIn the meantime, feel free to learn more about how we empower "
            "estate planning attorneys at wealthcounsel.com/about.\n\nBest,\nWealthCounsel "
            "Talent Team"
        ),
        "company": "WealthCounsel",
        "role": "Software Developer (Virtual, Full-Time)",
        "jd_url": (
            "https://wealthcounsel-llc.gnahiring.com/job/1013008/"
            "software-developer-virtual-full-time?d=2026-04-07+18%3A02%3A57+UTC&s=lif"
        ),
    },
    {
        "from": "priya.shah@chronograph.pe",
        "from_name": "Priya Shah (Chronograph)",
        "subject": "Chronograph — 30-min phone screen with engineering",
        "preview": (
            "Hi Timothy,\n\nI'm Priya on the Talent team at Chronograph — thanks for applying "
            "to the Software Engineer role. Your experience with distributed systems and "
            "data pipelines looks like a strong fit for our Data Platform team.\n\n"
            "I'd love to set up a 30-minute phone screen with our Engineering Manager, "
            "Marcus Chen, later this week. Could you share a couple of availability "
            "windows Thursday or Friday between 10am and 4pm ET?\n\nLooking forward,\n"
            "Priya"
        ),
        "company": "Chronograph",
        "role": "Software Engineer",
        "jd_url": (
            "https://job-boards.greenhouse.io/embed/job_app?"
            "for=chronograph&token=4802825007&utm_source=jobright"
        ),
    },
    {
        "from": "talentacquisition@fullsteam.com",
        "from_name": "Fullsteam Talent Acquisition",
        "subject": "Update on your Senior Developer application — Fullsteam",
        "preview": (
            "Dear Timothy,\n\nThank you for your interest in the Senior Developer (Remote, US) "
            "position at Fullsteam and for taking the time to interview with our team.\n\n"
            "After careful consideration, we regret to inform you that we will not be "
            "moving forward with your candidacy for this role. The decision was a difficult "
            "one — we received many strong applicants — and it is not a reflection of your "
            "talents or experience.\n\nWe'll keep your profile on file and would encourage "
            "you to apply again as new opportunities open up.\n\nWith appreciation,\n"
            "Fullsteam Talent Acquisition"
        ),
        "company": "Fullsteam",
        "role": "Senior Developer (Remote, US)",
        "jd_url": (
            "https://fullsteam.wd1.myworkdayjobs.com/External/"
            "job/Remote---US/Senior-Developer_JR102093"
        ),
    },
    {
        "from": "jordan.ramirez@bitsight.com",
        "from_name": "Jordan Ramirez (Bitsight Recruiting)",
        "subject": "Bitsight Full-Stack Engineer — technical interview scheduling",
        "preview": (
            "Hi Timothy,\n\nGreat chatting with you on Monday! The team really enjoyed the "
            "conversation and would like to move you to the next round — a 90-minute "
            "technical interview (virtual) with two engineers from the Ratings Platform "
            "team: a 45-minute system design discussion followed by a 45-minute coding "
            "session.\n\nCould you share 2–3 availability windows next Tuesday, Wednesday, "
            "or Thursday between 9am and 5pm ET so I can get a calendar invite out?\n\n"
            "Thanks,\nJordan Ramirez\nSenior Technical Recruiter, Bitsight"
        ),
        "company": "Bitsight",
        "role": "Software Engineer, Full-Stack",
        "jd_url": (
            "https://bitsight.wd1.myworkdayjobs.com/Bitsight/"
            "job/Remote-USA/Software-Engineer--Full-Stack_JR101221-1"
        ),
    },
    {
        "from": "sam.okafor@axios.com",
        "from_name": "Sam Okafor (Axios Recruiting)",
        "subject": "Axios onsite loop — scheduling",
        "preview": (
            "Hi Timothy,\n\nThanks for turning around the take-home so quickly. The engineers "
            "who reviewed it (Dana on Platform, Li-Wei on Newsroom Tools) were impressed "
            "with your write-up on trade-offs and caching strategy.\n\nWe'd like to move "
            "you to the onsite loop — four 45-minute virtual interviews back-to-back "
            "covering: coding, system design, cross-functional collaboration, and a chat "
            "with the hiring manager. Could you share your availability for next Tuesday "
            "or Wednesday?\n\nBest,\nSam\nRecruiting, Axios"
        ),
        "company": "Axios",
        "role": "Software Engineer",
        "jd_url": (
            "https://job-boards.greenhouse.io/embed/job_app?"
            "for=axios&token=7818788&utm_source=jobright"
        ),
    },
    {
        "from": "no-reply@greenhouse-mail.io",
        "from_name": "LTK Recruiting",
        "subject": "Thanks for applying to LTK — Software Engineer",
        "preview": (
            "Hi Timothy,\n\nThank you for applying to the Software Engineer role at LTK "
            "(formerly rewardStyle / LIKEtoKNOW.it). This note is to confirm that your "
            "application has been received and is now in our recruiting team's queue.\n\n"
            "We review every application and aim to respond within two weeks. If your "
            "background is a match for this role or another open position at LTK, a "
            "recruiter will reach out directly to set up an intro call.\n\nThanks again "
            "for your interest in LTK.\n\n— LTK Recruiting"
        ),
        "company": "LTK",
        "role": "Software Engineer",
        "jd_url": (
            "https://job-boards.greenhouse.io/embed/job_app?"
            "for=shopltk&token=7658417003&utm_source=jobright"
        ),
    },
]


class DemoSeedOut(BaseModel):
    ok: bool
    created_events: int
    created_suggestions: int


@router.post("/seed-demo", response_model=DemoSeedOut)
def seed_demo_emails(
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """Populate sample inbox events + suggestions for demos.
    Does NOT require real Outlook tokens — uses built-in fixtures so the
    email-analysis flow can be shown end-to-end.
    """
    if not _can_access_user(db, principal, user_id):
        raise HTTPException(status_code=403, detail="Not allowed")

    now = _now_utc()
    created_events = 0
    created_suggestions = 0

    # Bumping the "v" whenever the demo fixtures change forces a fresh seed
    # for users who already ran an earlier version of the demo.
    demo_version = "v3"

    for i, demo in enumerate(_DEMO_EMAILS):
        dedupe_id = f"demo-{demo_version}-{user_id}-{i}"
        existing = (
            db.query(EmailEvent)
            .filter(
                EmailEvent.user_id == user_id,
                EmailEvent.provider == "demo",
                EmailEvent.internet_message_id == dedupe_id,
            )
            .first()
        )
        if existing:
            continue

        # Upsert a demo Application so the email has a JD URL to link to.
        demo_app_id = f"demo-app-{demo_version}-{user_id}-{i}"
        app = db.query(Application).filter(Application.id == demo_app_id).first()
        if not app:
            app = Application(
                id=demo_app_id,
                user_id=user_id,
                company=demo["company"],
                role=demo["role"],
                url=demo["jd_url"],
                stage="applied",
                created_at=now,
                updated_at=now,
            )
            db.add(app)
            db.flush()

            # Seed a JobDescription row so the application has full context
            # (used by JD analysis, resume tailoring, and assistant grounding).
            jd_text = _DEMO_JDS.get(demo["company"])
            if jd_text:
                db.add(
                    JobDescription(
                        user_id=user_id,
                        application_id=app.id,
                        jd_text=jd_text,
                        created_at=now,
                    )
                )

        received = now - dt.timedelta(hours=i)
        ev = EmailEvent(
            user_id=user_id,
            provider="demo",
            message_id=dedupe_id,
            internet_message_id=dedupe_id,
            from_email=demo["from"],
            subject=demo["subject"],
            received_at=received,
            body_preview=demo["preview"],
            web_link=None,
            raw_json=None,
            created_at=now,
        )
        db.add(ev)
        db.flush()
        created_events += 1

        stage, stage_conf, stage_reason = _classify_email(
            ev.subject or "", ev.body_preview or ""
        )
        if stage == "unknown":
            continue

        # Direct match via the demo app we just upserted — higher confidence
        # than the keyword-based _match_application fallback.
        conf = min(100, int(0.6 * stage_conf + 0.4 * 90))

        sugg = ApplicationUpdateSuggestion(
            user_id=user_id,
            application_id=app.id,
            email_event_id=ev.id,
            suggested_stage=stage,
            confidence=conf,
            reason=f"{stage_reason}; matched to {demo['company']} demo application",
            status="pending",
            created_at=now,
            updated_at=now,
        )
        db.add(sugg)
        created_suggestions += 1

    db.commit()
    return DemoSeedOut(
        ok=True,
        created_events=created_events,
        created_suggestions=created_suggestions,
    )
