from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime
import base64, json, re

from app.db import SessionLocal
from app.models import Application, JobDescription, StoredFile, BaseResume, User
from app.auth import require_extension_token
from app.docx_render import render_resume
from app.storage import save_bytes
from app.ai import client

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ApplyIn(BaseModel):
    user_id: str = Field(..., min_length=1)
    url: str = Field(..., min_length=5)
    company: str = Field(..., min_length=1)
    position: str = Field(..., min_length=1)
    jd_text: str = Field(..., min_length=50)

def safe_filename(s: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", s).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:80] if s else "Document"

@router.post("/ingest/apply-and-generate", dependencies=[Depends(require_extension_token)])
def apply_and_generate(p: ApplyIn, db: Session = Depends(get_db)):
    # ensure user exists
    if not db.get(User, p.user_id):
        db.add(User(id=p.user_id))
        db.commit()

    base = db.get(BaseResume, p.user_id)
    if not base:
        raise HTTPException(400, "Base resume not set for user. PUT /v1/users/{user_id}/base-resume first.")

    # upsert application by (user_id, url)
    app = (
        db.query(Application)
        .filter(Application.user_id == p.user_id, Application.url == p.url)
        .first()
    )
    if not app:
        app = Application(user_id=p.user_id, company=p.company, role=p.position, url=p.url, stage="applied")
        db.add(app)
        db.commit()
        db.refresh(app)
    else:
        app.company = p.company
        app.role = p.position
        db.commit()

    # store JD
    db.add(JobDescription(user_id=p.user_id, application_id=app.id, jd_text=p.jd_text))
    db.commit()

    # Ask for strict JSON for your template placeholders
    prompt = f"""You are a resume tailoring system.
Return STRICT JSON only (no markdown, no commentary).
Keys required:
- SUMMARY: string
- SKILLS: string (comma-separated)
- EXP_COMPANY_1: string
- EXP_COMPANY_2: string
- EXP_COMPANY_3: string
- EXP_COMPANY_4: string

Rules:
- Use ONLY facts from BASE RESUME. Do NOT invent companies, titles, dates.
- Tailor wording to the JOB DESCRIPTION with relevant keywords.
- Each EXP_COMPANY_n should be 3-6 bullets separated by '\n' and starting with '• '.

JOB DESCRIPTION:
{p.jd_text}

BASE RESUME:
{base.content_text}
""".strip()

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    raw = resp.choices[0].message.content.strip()
    try:
        data = json.loads(raw)
    except Exception:
        raise HTTPException(500, f"Model did not return valid JSON. Raw: {raw[:400]}")

    # Render DOCX using your template
    docx_bytes = render_resume(data)

    company_fn = safe_filename(p.company)
    role_fn = safe_filename(p.position)
    filename = f"Resume_{company_fn}_{role_fn}.docx"
    path = save_bytes(p.user_id, app.id, filename, docx_bytes)

    sf = StoredFile(
        user_id=p.user_id,
        application_id=app.id,
        kind="resume_docx",
        path=path,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
        created_at=datetime.utcnow(),
    )
    db.add(sf)
    db.commit()
    db.refresh(sf)

    return {
        "application_id": app.id,
        "resume_docx_file_id": sf.id,
        "resume_docx_base64": base64.b64encode(docx_bytes).decode("ascii"),
        "resume_download_url": f"/v1/files/{sf.id}",
    }
