from __future__ import annotations

import base64
import datetime as dt
import json
import zipfile
from io import BytesIO
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
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
from .resume_builder import _generate_resume_bundle, GenerateResumeFromScratchIn

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
    include_cover_letter: bool = True
    position: str
    jd_text: str = ""
    have_to_generate: bool = True
    resume_json_text: Optional[str] = None


@router.post("/ingest/upload-tailored-resume")
async def upload_tailored_resume(
    application_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    app_row = db.get(Application, application_id)
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")

    _ensure_access(db, principal, app_row.user_id)

    filename = (file.filename or "").strip()
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed = {
        ".pdf": ("resume_pdf", "application/pdf"),
        # Keep Word uploads under the existing resume_docx kind so current
        # application listing code continues to expose the uploaded resume.
        ".doc": ("resume_docx", "application/msword"),
        ".docx": (
            "resume_docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    }
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Only .pdf, .doc, and .docx resume files are supported",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    now = dt.datetime.now()
    resume_kind, mime = allowed[ext]
    resume_version_id = (
        f"manual_edit_{app_row.id}_{now.strftime('%Y%m%d%H%M%S')}{now.microsecond}"
    )
    resume_version = ResumeVersion(
        id=resume_version_id,
        user_id=app_row.user_id,
        application_id=app_row.id,
        jd_key_id=None,
        schema_version="manual_upload_v1",
        tailored_json="{}",
        created_at=now,
    )
    db.add(resume_version)

    (
        db.query(StoredFile)
        .filter(
            StoredFile.application_id == app_row.id,
            StoredFile.kind.in_(["resume_docx", "resume_pdf"]),
        )
        .delete(synchronize_session=False)
    )

    user = db.get(User, app_row.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    file_id = f"file{now.strftime('%Y%m%d%H%M%S')}{now.microsecond}"
    rel_path = save_bytes(
        f"{user.name or user.id}-{user.id}",
        app_row.id,
        f"{file_id}{ext}",
        data,
    )
    stored = StoredFile(
        id=file_id,
        user_id=app_row.user_id,
        application_id=app_row.id,
        resume_version_id=resume_version_id,
        kind=resume_kind,
        path=rel_path,
        filename=filename or f"resume{ext}",
        mime=mime,
        created_at=now,
    )
    db.add(stored)

    app_row.updated_at = now
    db.commit()

    return {
        "application_id": app_row.id,
        "resume_version_id": resume_version_id,
        "stored_file_id": file_id,
        "kind": resume_kind,
        "filename": stored.filename,
        "mime": mime,
        "download_url": f"/v1/files/{file_id}/download",
    }


@router.post("/ingest/apply-and-generate")
def apply_and_generate(
    payload: ApplyAndGenerateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    _ensure_access(db, principal, payload.user_id)

    now = dt.datetime.now()
    # idempotent by (user_id, url)
    existing = (
        db.query(Application)
        .filter(Application.user_id == payload.user_id, Application.url == payload.url)
        .order_by(Application.created_at.desc())
        .first()
    )
    if existing:
        app_row = existing
        app_row.source_site = payload.source_site
        app_row.admin_id = principal.id if principal.type == "admin" else app_row.admin_id
        app_row.company = payload.company
        app_row.role = payload.position
        app_row.stage = "applied"
        app_row.updated_at = now

        jd_row = (
            db.query(JobDescription)
            .filter(JobDescription.application_id == app_row.id)
            .order_by(JobDescription.created_at.desc())
            .first()
        )
        if jd_row:
            jd_row.jd_text = payload.jd_text
        else:
            db.add(
                JobDescription(
                    user_id=payload.user_id,
                    application_id=app_row.id,
                    jd_text=payload.jd_text,
                )
            )
        db.flush()
    else:
        app_id = f"app{dt.datetime.now().strftime('%Y%m%d%H%M%S')}{dt.datetime.now().microsecond}"
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

    if not payload.have_to_generate:
        db.commit()
        return {
            "application_id": app_row.id,
            "message": "Application created without resume generation as requested",
        }

    keys = None
    if not (payload.resume_json_text or "").strip():
        keys = get_or_create_jd_keys(payload, db, principal)
    data = _generate_resume_bundle(
        GenerateResumeFromScratchIn(
            user_id=payload.user_id,
            jd_text=payload.jd_text,
            company=payload.company,
            position=payload.position,
            export_format="both",
            include_cover_letter=payload.include_cover_letter,
            resume_json_text=payload.resume_json_text or "",
        ),
        db,
        principal,
    )

    if data.get("blocked"):
        db.commit()
        out = {
            "application_id": app_row.id,
            "blocked": True,
            "block_reason": data.get("block_reason"),
        }
        if payload.include_cover_letter and "cover_letter" in data:
            out["cover_letter"] = data["cover_letter"]
        return out

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
        jd_key_id=keys.get("id") if keys else None,
        schema_version="manual_json_v1" if (payload.resume_json_text or "").strip() else "scratch_v1",
        tailored_json=json.dumps(data.get("resume_json") or {}, ensure_ascii=False),
        created_at=now,
    )
    db.add(rv)

    (
        db.query(StoredFile)
        .filter(
            StoredFile.application_id == app_row.id,
            StoredFile.kind.in_(["resume_docx", "resume_pdf"]),
        )
        .delete(synchronize_session=False)
    )

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
            **(
                {"cover_letter": data["cover_letter"]}
                if payload.include_cover_letter and "cover_letter" in data
                else {}
            ),
        }
    )
    out = {
        "application_id": app_row.id,
        "resume_version_id": rv_id,
        "resume_docx_file_id": file_id,
        "resume_pdf_file_id": resume_pdf_file_id,
        "resume_docx_download_url": f"/v1/files/{file_id}/download",
        "resume_pdf_download_url": (
            f"/v1/files/{resume_pdf_file_id}/download" if resume_pdf_file_id else None
        ),
    }
    if payload.include_cover_letter and "cover_letter" in data:
        out["cover_letter"] = data["cover_letter"]
    return out
