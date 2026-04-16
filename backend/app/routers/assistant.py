from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import Principal, get_db
from ..models import (
    AuthToken,
    Application,
    ApplicationUpdateSuggestion,
    EmailEvent,
)
from ..services.ai_service import AIService

router = APIRouter()

# In-memory store (dev). Later: persist to SQLite.
_THREADS: Dict[str, Dict[str, Any]] = {}
# shape:
# _THREADS[tid] = {"id": tid, "title": "...", "created_at": dt, "updated_at": dt, "messages": [MessageOut...]}


_ASSISTANT_MODEL = os.getenv("OPENAI_ASSISTANT_MODEL", "gpt-4.1-mini")
_MAX_CONTEXT_MESSAGES = 12
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)", re.IGNORECASE)
_VIEW_JD_LINK_RE = re.compile(r"\[View JD\]\(([^)]+)\)", re.IGNORECASE)
_REPLY_LINK_RE = re.compile(r"\[Reply via email\]\((mailto:[^)]+)\)", re.IGNORECASE)


class ThreadOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ThreadPatch(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


class MessageIn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)


class MessageOut(MessageIn):
    id: str
    created_at: datetime


def _now():
    return datetime.now()


def _get_principal_optional(
    db: Session,
    x_auth_token: Optional[str] = Header(default=None, alias="X-Auth-Token"),
) -> Optional[Principal]:
    """Best-effort principal lookup. Returns None if no/invalid token."""
    if not x_auth_token:
        return None
    row = db.query(AuthToken).filter(AuthToken.token == x_auth_token.strip()).first()
    if not row or row.principal_type not in ("user", "admin"):
        return None
    return Principal(
        type=row.principal_type,
        id=row.principal_id,
        name=getattr(row, "principal_name", None),
    )


def _build_user_context(db: Session, principal: Optional[Principal]) -> str:
    """Build a compact plaintext context block with the user's applications
    and recent email-derived suggestions. The assistant uses this to answer
    concrete questions like 'summarize recruiter emails from this week' or
    'what should I follow up on next?'."""
    if not principal or principal.type != "user":
        return ""

    lines: List[str] = []

    apps = (
        db.query(Application)
        .filter(Application.user_id == principal.id)
        .order_by(Application.updated_at.desc(), Application.created_at.desc())
        .all()
    )
    app_by_id = {a.id: a for a in apps}
    apps_for_summary = apps[:15]
    apps_with_jd = [a for a in apps if (a.url or "").strip()]
    if apps:
        lines.append("Recent applications:")
        for a in apps_for_summary:
            jd = (a.url or "").strip() or "(no url)"
            lines.append(
                f"- {a.company} — {a.role} [stage: {a.stage or 'applied'}] "
                f"| JD: {jd}"
            )

    suggestions = (
        db.query(ApplicationUpdateSuggestion, EmailEvent)
        .join(EmailEvent, EmailEvent.id == ApplicationUpdateSuggestion.email_event_id)
        .filter(ApplicationUpdateSuggestion.user_id == principal.id)
        .order_by(ApplicationUpdateSuggestion.created_at.desc())
        .limit(10)
        .all()
    )
    if suggestions:
        lines.append("")
        lines.append("Recent recruiter emails (auto-classified):")
        for sugg, ev in suggestions:
            subj = (ev.subject or "(no subject)").strip()
            sender = ev.from_email or "unknown"
            preview = (ev.body_preview or "").strip().replace("\n", " ")
            if len(preview) > 220:
                preview = preview[:220] + "..."
            haystack = " ".join(
                part.lower() for part in [subj, sender, preview] if part
            )
            # Try to surface the matched application's JD URL so the
            # assistant can link it in its reply.
            jd_url = ""
            company = ""
            if sugg.application_id and sugg.application_id in app_by_id:
                app = app_by_id[sugg.application_id]
                jd_url = (app.url or "").strip()
                company = app.company or ""
            if not jd_url:
                for app in apps_with_jd:
                    company_name = (app.company or "").strip()
                    if company_name and company_name.lower() in haystack:
                        jd_url = (app.url or "").strip()
                        company = company_name
                        break
            header = (
                f"- [{sugg.suggested_stage}] from {sender} — \"{subj}\" "
                f"(confidence {sugg.confidence}, status {sugg.status})"
            )
            lines.append(header)
            lines.append(
                f"    company: {company or '(unmatched)'} | "
                f"JD: {jd_url or '(none)'}"
            )
            if ev.web_link:
                lines.append(f"    open in mailbox: {ev.web_link}")
            if preview:
                lines.append(f"    preview: {preview}")

    return "\n".join(lines).strip()


def _fallback_reply(user_text: str, context: str) -> str:
    """Used when OpenAI is unavailable. Returns a readable canned response
    that still references the user context so the demo stays coherent."""
    base = (
        "I'm the CareerOS assistant. (Offline fallback — the OpenAI key isn't "
        "configured, so this is a canned reply.)"
    )
    if context:
        return (
            f"{base}\n\nHere's what I can see on your account right now:\n\n{context}"
        )
    return (
        f"{base}\n\nAsk me to tailor a resume, draft a cover letter, or review "
        "recruiter emails once the AI key is configured."
    )


def _build_link_facts(
    db: Session, principal: Optional[Principal]
) -> List[Dict[str, Optional[str]]]:
    if not principal or principal.type != "user":
        return []

    apps = (
        db.query(Application)
        .filter(Application.user_id == principal.id)
        .order_by(Application.updated_at.desc(), Application.created_at.desc())
        .all()
    )
    app_by_id = {a.id: a for a in apps}
    facts: List[Dict[str, Optional[str]]] = []

    for a in apps:
        company = (a.company or "").strip()
        if not company:
            continue
        facts.append(
            {
                "company": company,
                "jd_url": (a.url or "").strip() or None,
                "sender": None,
                "subject": None,
            }
        )

    suggestions = (
        db.query(ApplicationUpdateSuggestion, EmailEvent)
        .join(EmailEvent, EmailEvent.id == ApplicationUpdateSuggestion.email_event_id)
        .filter(ApplicationUpdateSuggestion.user_id == principal.id)
        .order_by(ApplicationUpdateSuggestion.created_at.desc())
        .limit(25)
        .all()
    )
    for sugg, ev in suggestions:
        app = app_by_id.get(sugg.application_id) if sugg.application_id else None
        company = (app.company if app else "") or ""
        jd_url = (app.url if app else "") or ""
        if not company:
            haystack = " ".join(
                ((ev.subject or ""), (ev.from_email or ""), (ev.body_preview or ""))
            ).lower()
            for candidate in apps:
                candidate_company = (candidate.company or "").strip()
                if candidate_company and candidate_company.lower() in haystack:
                    company = candidate_company
                    jd_url = (candidate.url or "").strip()
                    break
        company = company.strip()
        if not company:
            continue
        facts.append(
            {
                "company": company,
                "jd_url": jd_url or None,
                "sender": (ev.from_email or "").strip() or None,
                "subject": (ev.subject or "").strip() or None,
            }
        )

    return facts


def _match_link_fact(
    line: str, facts: List[Dict[str, Optional[str]]]
) -> Optional[Dict[str, Optional[str]]]:
    line_lower = line.lower()
    matches = []
    for fact in facts:
        company = (fact.get("company") or "").strip()
        if company and company.lower() in line_lower:
            matches.append(fact)
    if not matches:
        return None
    return max(matches, key=lambda x: len((x.get("company") or "").strip()))


def _line_needs_reply(line: str) -> bool:
    line_lower = line.lower()
    if any(
        phrase in line_lower
        for phrase in (
            "no action needed",
            "no immediate action needed",
            "wait for",
            "under review",
            "rejected",
            "not selected",
        )
    ):
        return False
    return any(
        phrase in line_lower
        for phrase in (
            "reply",
            "schedule",
            "confirm",
            "availability",
            "available",
            "share your availability",
            "share availability",
            "time works",
            "times that work",
            "time slots",
            "calendar",
            "follow up",
            "reach out",
            "send",
            "phone screen",
            "intro call",
            "screening call",
            "next round",
            "move forward",
            "technical interview",
            "onsite",
            "onsite loop",
            "interview",
        )
    )


def _build_reply_mailto(line: str, fact: Dict[str, Optional[str]]) -> Optional[str]:
    sender = (fact.get("sender") or "").strip()
    if "@" not in sender:
        return None

    subject = (fact.get("subject") or "").strip()
    if subject and not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    if not subject:
        subject = f"Follow-up on {fact.get('company') or 'this opportunity'}"

    line_lower = line.lower()
    if any(
        word in line_lower
        for word in (
            "schedule",
            "availability",
            "available",
            "phone screen",
            "intro call",
            "screening call",
            "technical interview",
            "onsite",
            "interview",
            "calendar",
        )
    ):
        body = (
            "Hi,\n\n"
            "Thanks for reaching out. I'd be happy to continue the process. "
            "Here are a few times that work for me:\n"
            "- \n- \n\n"
            "Please let me know what works best.\n\n"
            "Best,"
        )
    elif "follow up" in line_lower:
        body = (
            "Hi,\n\n"
            "I'm following up on this opportunity and remain very interested. "
            "Please let me know if there are any updates or anything else you need from me.\n\n"
            "Best,"
        )
    else:
        body = (
            "Hi,\n\n"
            "Thanks for the update. I'm happy to continue the process and can provide "
            "anything else you need.\n\n"
            "Best,"
        )

    return f"mailto:{sender}?subject={quote(subject)}&body={quote(body)}"


def _line_has_jd_link(line: str, jd_url: Optional[str]) -> bool:
    if not line or not jd_url:
        return bool(_VIEW_JD_LINK_RE.search(line)) if line else False
    jd_url = jd_url.strip()
    for match in _VIEW_JD_LINK_RE.finditer(line):
        if (match.group(1) or "").strip() == jd_url:
            return True
    return bool(_VIEW_JD_LINK_RE.search(line))


def _line_has_reply_link(line: str) -> bool:
    if not line:
        return False
    return bool(_REPLY_LINK_RE.search(line) or re.search(r"mailto:", line, re.IGNORECASE))


def _dedupe_view_jd_links(line: str) -> str:
    if not line:
        return line

    seen_view_jd = False

    def repl(match: re.Match[str]) -> str:
        nonlocal seen_view_jd
        if seen_view_jd:
            return ""
        seen_view_jd = True
        return match.group(0)

    deduped = _VIEW_JD_LINK_RE.sub(repl, line)
    deduped = re.sub(r"[ \t]{2,}", " ", deduped).strip()
    return deduped


def _remove_view_jd_links(line: str) -> str:
    if not line:
        return line

    cleaned = _VIEW_JD_LINK_RE.sub("", line)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned


def _line_starts_new_list_item(line: str) -> bool:
    stripped = line.lstrip()
    return bool(re.match(r"^(?:[-*]|\d+\.)\s+", stripped))


def _dedupe_view_jd_across_lines(text: str) -> str:
    if not text:
        return text

    out_lines: List[str] = []
    current_item_has_view_jd = False

    for raw_line in text.splitlines():
        line = _dedupe_view_jd_links(raw_line.rstrip())
        stripped = line.strip()

        if not stripped:
            out_lines.append(line)
            current_item_has_view_jd = False
            continue

        starts_new_item = _line_starts_new_list_item(line)
        if starts_new_item:
            current_item_has_view_jd = False

        if current_item_has_view_jd and _line_has_jd_link(line, None):
            line = _remove_view_jd_links(line)

        if _line_has_jd_link(line, None):
            current_item_has_view_jd = True

        out_lines.append(line)

    return "\n".join(out_lines)


def _inject_assistant_links(
    text: str, facts: List[Dict[str, Optional[str]]]
) -> str:
    if not text.strip() or not facts:
        return text

    out_lines: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        fact = _match_link_fact(line, facts)
        if not fact:
            out_lines.append(raw_line)
            continue

        additions: List[str] = []
        if not _line_has_jd_link(line, fact.get("jd_url")) and fact.get("jd_url"):
            additions.append(f"[View JD]({fact['jd_url']})")

        if not _line_has_reply_link(line) and _line_needs_reply(line):
            mailto = _build_reply_mailto(line, fact)
            if mailto:
                additions.append(f"[Reply via email]({mailto})")

        if additions:
            line = f"{line} {' '.join(additions)}"
        out_lines.append(line)

    return _dedupe_view_jd_across_lines("\n".join(out_lines))


def _run_openai_chat(
    *,
    user_text: str,
    prior_messages: List[Dict[str, Any]],
    context: str,
) -> str:
    """Call OpenAI chat completions and return the reply text."""
    if not os.getenv("OPENAI_API_KEY"):
        return _fallback_reply(user_text, context)

    system_prompt = (
        "You are CareerOS Assistant — a focused job-search copilot. "
        "You help the user tailor resumes, draft cover letters, and triage "
        "recruiter emails. Be concise, practical, and action-oriented.\n\n"
        "Grounding rules:\n"
        "- When the user asks about their emails, applications, or profile, "
        "answer only from the data block below.\n"
        "- If the data does not contain the answer, reply naturally like a "
        "human would — e.g. 'I don't have that information yet' or 'I don't "
        "see any recruiter emails from this week'. Do NOT say phrases like "
        "'in the provided context', 'based on the context', 'the context "
        "doesn't include', or refer to a context/data block at all. The "
        "user doesn't know a context block exists.\n"
        "- Never invent data you were not given.\n\n"
        "Linking rules (very important for usability):\n"
        "- Always use markdown links in the form [label](url).\n"
        "- When you mention a specific job/recruiter email, append a "
        "[View JD](JD url) link whenever a JD url is present for that "
        "application, so the user can open the job description.\n"
        "- If you produce a numbered summary or 'next steps' list about "
        "applications or recruiter emails, include a [View JD](JD url) link "
        "on every item using the matching JD from the user data whenever a "
        "JD url is available.\n"
        "- If an item genuinely requires the user to respond to the recruiter, "
        "append a [Reply via email](mailto:...) link on that same line. Do "
        "this whenever possible.\n"
        "- This includes cases like confirming availability, scheduling phone "
        "screens or interviews, responding to an intro call, sharing time "
        "windows, answering a direct recruiter request, or sending follow-up "
        "information.\n"
        "- When you add [Reply via email](mailto:...), include a pre-filled "
        "subject and body. Build the mailto like: "
        "mailto:<sender>?subject=<urlencoded subject>&body=<urlencoded body>. "
        "Prefix the subject with 'Re: ' when replying. URL-encode spaces as "
        "%20 and newlines as %0A. Keep the draft body short, professional, "
        "and specific to the email's intent.\n"
        "- In summaries and action lists, prefer including the reply link "
        "immediately rather than merely telling the user they should reply.\n"
        "- Do not add [Reply via email](mailto:...) for items that do not "
        "need a response yet, such as acknowledgements, passive review "
        "updates, or completed/rejected outcomes.\n"
        "- Never output naked mailto: or https: URLs — always wrap them in "
        "[label](url)."
    )
    if context:
        system_prompt += f"\n\n---\nUser data:\n{context}\n---"

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    # Only the last N prior messages to keep prompts small
    for m in prior_messages[-_MAX_CONTEXT_MESSAGES:]:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_text})

    try:
        svc = AIService()
        resp = svc.client.chat.completions.create(
            model=_ASSISTANT_MODEL,
            messages=messages,
            temperature=0.4,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or _fallback_reply(user_text, context)
    except Exception as e:  # noqa: BLE001
        # Don't crash the demo — surface a readable fallback.
        return (
            f"{_fallback_reply(user_text, context)}\n\n(AI call failed: "
            f"{type(e).__name__}: {str(e)[:200]})"
        )


def _derive_title(first_user_text: str) -> str:
    t = (first_user_text or "").strip().replace("\n", " ")
    if not t:
        return "New chat"
    return (t[:60] + "…") if len(t) > 60 else t


@router.get("/assistant/threads", response_model=List[ThreadOut])
def list_threads():
    items = list(_THREADS.values())
    items.sort(key=lambda x: x["updated_at"], reverse=True)
    return [
        ThreadOut(
            id=t["id"],
            title=t["title"],
            created_at=t["created_at"],
            updated_at=t["updated_at"],
        )
        for t in items
    ]


@router.post("/assistant/threads", response_model=ThreadOut)
def create_thread():
    tid = str(uuid.uuid4())
    now = _now()
    _THREADS[tid] = {
        "id": tid,
        "title": "New chat",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    t = _THREADS[tid]
    return ThreadOut(
        id=t["id"],
        title=t["title"],
        created_at=t["created_at"],
        updated_at=t["updated_at"],
    )


@router.patch("/assistant/threads/{thread_id}", response_model=ThreadOut)
def rename_thread(thread_id: str, payload: ThreadPatch):
    if thread_id not in _THREADS:
        raise HTTPException(status_code=404, detail="Thread not found")
    _THREADS[thread_id]["title"] = payload.title.strip()
    _THREADS[thread_id]["updated_at"] = _now()
    t = _THREADS[thread_id]
    return ThreadOut(
        id=t["id"],
        title=t["title"],
        created_at=t["created_at"],
        updated_at=t["updated_at"],
    )


@router.delete("/assistant/threads/{thread_id}")
def delete_thread(thread_id: str):
    if thread_id not in _THREADS:
        raise HTTPException(status_code=404, detail="Thread not found")
    del _THREADS[thread_id]
    return {"ok": True}


@router.get("/assistant/threads/{thread_id}/messages", response_model=List[MessageOut])
def list_messages(thread_id: str):
    if thread_id not in _THREADS:
        raise HTTPException(status_code=404, detail="Thread not found")
    return _THREADS[thread_id]["messages"]


@router.post("/assistant/threads/{thread_id}/messages", response_model=MessageOut)
def add_message(
    thread_id: str,
    payload: MessageIn,
    db: Session = Depends(get_db),
    x_auth_token: Optional[str] = Header(default=None, alias="X-Auth-Token"),
):
    if thread_id not in _THREADS:
        # auto-create if missing
        now = _now()
        _THREADS[thread_id] = {
            "id": thread_id,
            "title": "New chat",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }

    thread = _THREADS[thread_id]

    msg = MessageOut(
        id=str(uuid.uuid4()),
        created_at=_now(),
        role=payload.role,
        content=payload.content,
    )
    thread["messages"].append(msg)
    thread["updated_at"] = _now()

    # Auto-title thread from first user message
    if payload.role == "user" and thread["title"] in ("", "New chat"):
        thread["title"] = _derive_title(payload.content)

    if payload.role != "user":
        return msg

    # Build context + prior messages for OpenAI
    principal = _get_principal_optional(db, x_auth_token)
    context = _build_user_context(db, principal)
    link_facts = _build_link_facts(db, principal)
    prior = [
        {"role": m.role, "content": m.content}
        for m in thread["messages"][:-1]  # exclude the message we just added
        if isinstance(m, MessageOut)
    ]

    reply_text = _run_openai_chat(
        user_text=payload.content,
        prior_messages=prior,
        context=context,
    )
    reply_text = _inject_assistant_links(reply_text, link_facts)

    reply = MessageOut(
        id=str(uuid.uuid4()),
        created_at=_now(),
        role="assistant",
        content=reply_text,
    )
    thread["messages"].append(reply)
    thread["updated_at"] = _now()
    return reply
