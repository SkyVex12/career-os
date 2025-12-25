
from __future__ import annotations

import base64
import datetime as dt
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sqlalchemy.orm import Session

from ..auth import Principal, get_db, get_principal
from ..models import AdminUser, Application, BaseResume, StoredFile
from ..storage import save_bytes
from ..docx_render import render_resume


router = APIRouter(prefix="/v1", tags=["ingest"])


def _admin_user_ids(db: Session, admin_id: str) -> List[str]:
    return [r.user_id for r in db.query(AdminUser).filter(AdminUser.admin_id == admin_id).all()]


def _ensure_access(db: Session, principal: Principal, user_id: str) -> None:
    if principal.type == "user":
        if principal.id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        return
    # admin
    ok = db.query(AdminUser).filter(AdminUser.admin_id == principal.id, AdminUser.user_id == user_id).first()
    if not ok:
        raise HTTPException(status_code=403, detail="Forbidden")


def _load_base_resume_context(db: Session, user_id: str) -> Dict[str, Any]:
    br = db.query(BaseResume).filter(BaseResume.user_id == user_id).order_by(BaseResume.created_at.desc()).first()
    if not br or not br.content_text:
        return {}
    txt = br.content_text.strip()
    try:
        return json.loads(txt)
    except Exception:
        return {"base_resume_text": txt}


class ApplyAndGenerateIn(BaseModel):
    user_id: str
    url: str
    company: str
    position: str
    jd_text: str


@router.post("/ingest/apply-and-generate")
def apply_and_generate(
    payload: ApplyAndGenerateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    _ensure_access(db, principal, payload.user_id)

    now = dt.datetime.utcnow()
    # idempotent by (user_id, url)
    existing = db.query(Application).filter(Application.user_id == payload.user_id, Application.url == payload.url).order_by(Application.created_at.desc()).first()
    if existing:
        app_row = existing
    else:
        app_id = f"app{now.strftime('%Y%m%d%H%M%S')}{now.microsecond}"
        app_row = Application(
            id=app_id,
            user_id=payload.user_id,
            url=payload.url,
            company=payload.company,
            role=payload.position,
            stage="applied",
            created_at=now,
            updated_at=now,
            created_by_type=principal.type,
            created_by_id=principal.id,
        )
        db.add(app_row)

    # render docx
    ctx = _load_base_resume_context(db, payload.user_id)
    ctx = {**ctx, "target_company": payload.company, "target_role": payload.position, "job_url": payload.url, "job_description": payload.jd_text}

    docx_bytes = render_resume(ctx)

    file_id = f"file{now.strftime('%Y%m%d%H%M%S')}{now.microsecond}"
    rel_path = save_bytes(file_id + ".docx", docx_bytes)
    stored = StoredFile(id=file_id, path=rel_path, filename="resume.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", created_at=now)
    db.add(stored)
    app_row.resume_docx_file_id = file_id
    db.commit()

    return {
        "application_id": app_row.id,
        "resume_docx_file_id": file_id,
        "resume_download_url": f"/v1/files/{file_id}/download",
        "resume_docx_base64": base64.b64encode(docx_bytes).decode("utf-8"),
    }


class ApplyAndGenerateBatchIn(BaseModel):
    url: str
    company: str
    position: str
    jd_text: str


@router.post("/ingest/apply-and-generate/batch")
def apply_and_generate_batch(
    payload: ApplyAndGenerateBatchIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    if principal.type != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    user_ids = _admin_user_ids(db, principal.id)
    now = dt.datetime.utcnow()
    results = []
    for uid in user_ids:
        try:
            # create per-user
            existing = db.query(Application).filter(Application.user_id == uid, Application.url == payload.url).order_by(Application.created_at.desc()).first()
            if existing:
                app_row = existing
            else:
                app_id = f"app{dt.datetime.utcnow().strftime('%Y%m%d%H%M%S')}{dt.datetime.utcnow().microsecond}"
                app_row = Application(
                    id=app_id,
                    user_id=uid,
                    url=payload.url,
                    company=payload.company,
                    role=payload.position,
                    stage="applied",
                    created_at=dt.datetime.utcnow(),
                    updated_at=dt.datetime.utcnow(),
                    created_by_type=principal.type,
                    created_by_id=principal.id,
                )
                db.add(app_row)

            ctx = _load_base_resume_context(db, uid)
            ctx = {**ctx, "target_company": payload.company, "target_role": payload.position, "job_url": payload.url, "job_description": payload.jd_text}
            docx_bytes = render_resume(ctx)

            file_id = f"file{dt.datetime.utcnow().strftime('%Y%m%d%H%M%S')}{dt.datetime.utcnow().microsecond}"
            rel_path = save_bytes(file_id + ".docx", docx_bytes)
            stored = StoredFile(id=file_id, path=rel_path, filename="resume.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", created_at=dt.datetime.utcnow())
            db.add(stored)
            app_row.resume_docx_file_id = file_id
            db.flush()

            results.append({
                "ok": True,
                "user_id": uid,
                "application_id": app_row.id,
                "resume_docx_file_id": file_id,
                "resume_download_url": f"/v1/files/{file_id}/download",
                "resume_docx_base64": base64.b64encode(docx_bytes).decode("utf-8"),
            })
        except Exception as e:
            results.append({"ok": False, "user_id": uid, "error": str(e)})

    db.commit()
    return {"results": results}
