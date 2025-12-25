from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime
import base64, json, os

from openai import OpenAI

from ..db import SessionLocal
from ..models import Application, BaseResume, JobDescription, StoredFile, User
from ..auth import get_principal, Principal, assert_user_access
from ..docx_render import render_resume
from ..storage import save_bytes, safe_filename

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ApplyGenerateIn(BaseModel):
    user_id: str
    url: str
    company: str
    position: str
    jd_text: str = Field(..., min_length=50)

class ApplyGenerateBatchIn(BaseModel):
    url: str
    company: str
    position: str
    jd_text: str = Field(..., min_length=50)
    target_user_ids: list[str] | None = None

def _ensure_user(db: Session, user_id: str, admin_id: str | None = None):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        u = User(id=user_id, admin_id=admin_id, name=None)
        db.add(u)
        db.commit()
    return u

def _generate_for_user(db: Session, user_id: str, url: str, company: str, position: str, jd_text: str):
    base = db.query(BaseResume).filter(BaseResume.user_id == user_id).first()
    if not base:
        raise HTTPException(400, f"Base resume missing for user_id={user_id}")

    app = db.query(Application).filter(Application.user_id == user_id, Application.url == url).first()
    if not app:
        app = Application(user_id=user_id, company=company, role=position, url=url, stage="applied", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.add(app)
        db.commit()
        db.refresh(app)
    else:
        app.company = company
        app.role = position
        app.updated_at = datetime.utcnow()
        db.commit()

    db.add(JobDescription(user_id=user_id, application_id=app.id, jd_text=jd_text, created_at=datetime.utcnow()))
    db.commit()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(500, "OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key)

    prompt = f"""
You are an expert resume writer. Based on the JOB DESCRIPTION and the BASE RESUME below, output ONLY valid JSON with these keys:
- name, title, summary (string), skills (list of strings), experience (list of objects with: company, role, bullets(list)), education (list of strings)

Rules:
- Tailor bullets to match the job description.
- Keep results professional and concise.
- Do not include markdown. Return JSON only.

JOB DESCRIPTION:
{jd_text}

BASE RESUME:
{base.content_text}
""".strip()

    resp = client.chat.completions.create(
        model=os.getenv("CAREEROS_MODEL", "gpt-4o-mini"),
        messages=[{"role":"user","content":prompt}],
        temperature=0.2,
    )

    raw = (resp.choices[0].message.content or "").strip()
    try:
        data = json.loads(raw)
    except Exception:
        raise HTTPException(500, f"Model did not return valid JSON. Raw: {raw[:400]}")

    docx_bytes = render_resume(data)

    company_fn = safe_filename(company)
    role_fn = safe_filename(position)
    filename = f"Resume_{company_fn}_{role_fn}.docx"
    path = save_bytes(user_id, app.id, filename, docx_bytes)

    sf = StoredFile(
        user_id=user_id,
        application_id=app.id,
        kind="resume_docx",
        path=str(path),
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
        created_at=datetime.utcnow(),
    )
    db.add(sf)
    db.commit()
    db.refresh(sf)

    return {
        "user_id": user_id,
        "application_id": app.id,
        "resume_docx_file_id": sf.id,
        "resume_download_url": f"/v1/files/{sf.id}",
        "resume_docx_base64": base64.b64encode(docx_bytes).decode("ascii"),
        "filename": filename,
    }

@router.post("/ingest/apply-and-generate")
def apply_and_generate(
    p: ApplyGenerateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    assert_user_access(principal, p.user_id, db)
    _ensure_user(db, p.user_id, principal.get("admin_id"))
    out = _generate_for_user(db, p.user_id, p.url, p.company, p.position, p.jd_text)
    return {k: v for k, v in out.items() if k != "user_id"}  # keep response compatible

@router.post("/ingest/apply-and-generate/batch")
def apply_and_generate_batch(
    p: ApplyGenerateBatchIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    if principal["type"] != "admin":
        raise HTTPException(403, "Batch endpoint is admin-only")

    users = db.query(User).filter(User.admin_id == principal["admin_id"]).order_by(User.id.asc()).all()
    allowed = set(u.id for u in users)
    targets = [uid for uid in (p.target_user_ids or list(allowed)) if uid in allowed]

    results = []
    for uid in targets:
        try:
            _ensure_user(db, uid, principal["admin_id"])
            r = _generate_for_user(db, uid, p.url, p.company, p.position, p.jd_text)
            r["ok"] = True
            results.append(r)
        except HTTPException as e:
            results.append({"user_id": uid, "ok": False, "error": e.detail})
        except Exception as e:
            results.append({"user_id": uid, "ok": False, "error": str(e)})

    return {"ok": True, "results": results}
