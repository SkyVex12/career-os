from __future__ import annotations

import base64
import datetime as dt
import json
import zipfile
from io import BytesIO
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sqlalchemy.orm import Session

from ..auth import Principal, get_db, get_principal
from ..models import (
    AdminUser,
    Application,
    BaseResume,
    StoredFile,
    ResumeVersion,
    User,
    JobDescription,
)
from ..storage import save_bytes
from .jd import get_or_create_jd_keys
from .resume_builder import export_tailored_docx, ExportTailoredDocxIn

router = APIRouter(prefix="/v1", tags=["ingest"])


def _ensure_access(db: Session, principal: Principal, user_id: str) -> None:
    if principal.type == "user":
        if principal.id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        return
    # admin
    ok = (
        db.query(AdminUser)
        .filter(AdminUser.admin_id == principal.id, AdminUser.user_id == user_id)
        .first()
    )
    if not ok:
        raise HTTPException(status_code=403, detail="Forbidden")


class ApplyAndGenerateIn(BaseModel):
    user_id: str
    url: str
    source_site: Optional[str] = None
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
    existing = (
        db.query(Application)
        .filter(Application.user_id == payload.user_id, Application.url == payload.url)
        .order_by(Application.created_at.desc())
        .first()
    )
    if existing:
        app_row = existing
    else:
        app_id = f"app{dt.datetime.utcnow().strftime('%Y%m%d%H%M%S')}{dt.datetime.utcnow().microsecond}"
        app_row = Application(
            id=app_id,
            user_id=payload.user_id,
            source_site=payload.source_site,
            admin_id=principal.id if principal.type == "admin" else None,
            url=payload.url,
            company=payload.company,
            role=payload.position,
            stage="applied",
            created_at=now,
            updated_at=now,
        )
        print("before add app: in transaction?", db.in_transaction())
        db.add(app_row)
        db.flush()
        print("after flush app exists?", db.get(Application, app_row.id) is not None)

        jd_row = JobDescription(
            user_id=payload.user_id,
            application_id=app_row.id,
            jd_text=payload.jd_text,
        )
        db.add(jd_row)
        db.flush()
        print(
            "after flush jd exists?",
            db.query(JobDescription).filter_by(application_id=app_row.id).count(),
        )

    keys = get_or_create_jd_keys(payload, db, principal)
    data = export_tailored_docx(
        ExportTailoredDocxIn(
            user_id=payload.user_id, jd_key_id=keys["id"], export_format="both"
        ),
        db,
        principal,
    )

    # export endpoint returns a zip bundle when export_format="both"
    if "bundle_zip_base64" in data:
        zbytes = base64.b64decode(data["bundle_zip_base64"])
        zf = zipfile.ZipFile(BytesIO(zbytes))
        docx_bytes = zf.read("resume.docx")
        pdf_bytes = zf.read("resume.pdf")
    else:
        docx_bytes = base64.b64decode(data["resume_docx_base64"])
        pdf_bytes = None

    # Resume versioning
    rv_id = f"rv{now.strftime('%Y%m%d%H%M%S')}{now.microsecond}"
    rv = ResumeVersion(
        id=rv_id,
        user_id=payload.user_id,
        application_id=app_row.id,
        jd_key_id=keys.get("id"),
        schema_version="tailor_v2",
        tailored_json=json.dumps(data.get("ai_output") or {}, ensure_ascii=False),
        created_at=now,
    )
    db.add(rv)

    file_id = f"file{now.strftime('%Y%m%d%H%M%S')}{now.microsecond}"
    user = db.get(User, payload.user_id)
    rel_path = save_bytes(
        f"{user.name}-{user.id}", app_row.id, file_id + ".docx", docx_bytes
    )
    stored = StoredFile(
        id=file_id,
        user_id=payload.user_id,
        application_id=app_row.id,
        resume_version_id=rv_id,
        kind="resume_docx",
        path=rel_path,
        filename="resume.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        created_at=now,
    )
    db.add(stored)
    db.flush()
    print(
        "after flush stored files:",
        db.query(StoredFile).filter_by(application_id=app_row.id).count(),
    )

    resume_pdf_file_id = None
    if pdf_bytes:
        resume_pdf_file_id = f"file{now.strftime('%Y%m%d%H%M%S')}{now.microsecond}p"
        pdf_path = save_bytes(
            f"{user.name}-{user.id}", app_row.id, resume_pdf_file_id + ".pdf", pdf_bytes
        )
        stored_pdf = StoredFile(
            id=resume_pdf_file_id,
            user_id=payload.user_id,
            application_id=app_row.id,
            resume_version_id=rv_id,
            kind="resume_pdf",
            path=pdf_path,
            filename="resume.pdf",
            mime="application/pdf",
            created_at=now,
        )
        db.add(stored_pdf)
        db.flush()
        print(
            "after flush stored files:",
            db.query(StoredFile).filter_by(application_id=app_row.id).count(),
        )

    db.commit()
    print(
        {
            "application_id": app_row.id,
            "resume_version_id": rv_id,
            "resume_docx_file_id": file_id,
            "resume_pdf_file_id": resume_pdf_file_id,
            "resume_docx_download_url": f"/v1/files/{file_id}/download",
            "resume_pdf_download_url": (
                f"/v1/files/{resume_pdf_file_id}/download"
                if resume_pdf_file_id
                else None
            ),
            "cover_letter": data["cover_letter"],
        }
    )
    return {
        "application_id": app_row.id,
        "resume_version_id": rv_id,
        "resume_docx_file_id": file_id,
        "resume_pdf_file_id": resume_pdf_file_id,
        "resume_docx_download_url": f"/v1/files/{file_id}/download",
        "resume_pdf_download_url": (
            f"/v1/files/{resume_pdf_file_id}/download" if resume_pdf_file_id else None
        ),
        "cover_letter": data["cover_letter"],
    }
