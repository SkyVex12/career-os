from __future__ import annotations

import base64
import json
import re
import requests
import zipfile
from io import BytesIO
from typing import Any, Dict, List, Set

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import Principal, get_principal
from ..db import SessionLocal
from ..models import AdminUser, BaseResume, JDKeyInfo, StoredFile, User
from ..resume_docx import replace_bullets_in_docx, replace_summary_in_docx
from ..pdf import resume_to_pdf_bytes
from ..ai import tailor_rewrite_resume
from ..services.pdf_service import docx_bytes_to_pdf_bytes

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------
# Text helpers
# ---------------------------


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _tokenize(s: str) -> List[str]:
    s = _norm(s)
    s = re.sub(r"[^a-z0-9+#/.-]+", " ", s)
    return [t for t in s.split(" ") if t]


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items or []:
        k = _norm(str(x))
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(str(x))
    return out


def _phrase_hit(bullet: str, phrase: str) -> bool:
    btoks = set(_tokenize(bullet))
    ptoks = set(_tokenize(phrase))
    return bool(btoks and ptoks and (btoks & ptoks))


def _compute_hits_for_bullet(
    bullet: str,
    core_hard: List[str],
    core_soft: List[str],
    required_phrases: List[str],
) -> List[str]:
    hits: List[str] = []
    for p in core_hard:
        if _phrase_hit(bullet, p):
            hits.append(p)
    for p in core_soft:
        if _phrase_hit(bullet, p):
            hits.append(p)
    for p in required_phrases:
        if _phrase_hit(bullet, p):
            hits.append(p)
    return _dedupe_keep_order(hits)


# ---------------------------
# Access control
# ---------------------------


def _check_access(db: Session, principal: Principal, user_id: str) -> None:
    if principal.type == "user":
        if principal.id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
    else:
        ok = (
            db.query(AdminUser)
            .filter(AdminUser.admin_id == principal.id, AdminUser.user_id == user_id)
            .first()
        )
        if ok is None:
            raise HTTPException(status_code=403, detail="Forbidden")


# ---------------------------
# Resume loading
# ---------------------------


def _load_base_resume_json(br: BaseResume) -> Dict[str, Any]:
    txt = br.content_text or ""
    try:
        obj = json.loads(txt)
        if isinstance(obj, dict) and ("experiences" in obj):
            return obj
    except Exception as e:
        print("---------------", e)
        pass

    bullets: List[str] = []
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith(("•", "-", "*", "●")):
            bullets.append(s.lstrip("●•-* ").strip())

    return {
        "schema": "resume_json_fallback_v1",
        "summary": "",
        "summary_para_idxs": [],
        "experiences": [{"header": "", "bullets": bullets, "bullet_para_idxs": []}],
    }


# ---------------------------
# API Models
# ---------------------------


class TailorBulletsIn(BaseModel):
    user_id: str
    jd_key_id: int
    bullets_per_role: int = Field(default=5, ge=1, le=10)  # kept for compat
    max_roles: int = Field(default=4, ge=1, le=10)
    include_cover_letter: bool = False
    cover_letter_instructions: str = ""


class TailorBulletsOut(BaseModel):
    selected_experiences: List[Dict[str, Any]]
    keywords_covered: List[str]
    gaps: List[str]
    summary: str = ""
    cover_letter: str = ""


# ---------------------------
# Endpoint: tailor bullets + summary (ONE OPENAI CALL)
# ---------------------------


@router.post("/v1/resume/tailor-bullets", response_model=TailorBulletsOut)
def tailor_bullets(
    payload: TailorBulletsIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    _check_access(db, principal, payload.user_id)

    br = db.get(BaseResume, payload.user_id)
    if not br:
        print("br+++++++++++++++++")
        raise HTTPException(status_code=404, detail="Base resume not found")

    jd = db.get(JDKeyInfo, payload.jd_key_id)
    if not jd:
        print("jd+++++++++++++++++")
        raise HTTPException(status_code=404, detail="JD keys not found")

    resume = _load_base_resume_json(br)
    exps = resume.get("experiences") or []
    if not isinstance(exps, list) or not exps:
        raise HTTPException(
            status_code=400, detail="Base resume JSON has no experiences"
        )

    # JD keys
    try:
        jd_keys = json.loads(jd.keys_json or "{}")
        if not isinstance(jd_keys, dict):
            jd_keys = {}
    except Exception:
        jd_keys = {}

    core_hard = _dedupe_keep_order(jd_keys.get("core_hard") or [])
    core_soft = _dedupe_keep_order(jd_keys.get("core_soft") or [])
    required_phrases = _dedupe_keep_order(jd_keys.get("required_phrases") or [])

    # Build inputs for ONE call
    summary_original = (resume.get("summary") or "").strip()

    exp_bullets_list: List[List[str]] = []
    exp_meta_list: List[Dict[str, Any]] = []
    for exp in exps[: payload.max_roles]:
        bullets = [str(b).strip() for b in (exp.get("bullets") or []) if str(b).strip()]
        if not bullets:
            continue
        exp_bullets_list.append(bullets)
        # keep meta to return
        exp_meta_list.append(
            {
                "header": exp.get("header"),
                "company": exp.get("company"),
                "title": exp.get("title"),
                "start": exp.get("start"),
                "end": exp.get("end"),
                "location": exp.get("location"),
            }
        )

    # ONE OpenAI call
    try:
        ai = tailor_rewrite_resume(
            summary_text=summary_original,
            experiences=exp_bullets_list,
            core_hard=core_hard,
            core_soft=core_soft,
            required_phrases=required_phrases,
            include_cover_letter=payload.include_cover_letter,
            cover_letter_instructions=payload.cover_letter_instructions,
        )
    except Exception as e:
        print("AI error:", e)
        # Fail closed: no AI changes
        covered_all: Set[str] = set()
        selected: List[Dict[str, Any]] = []
        for k, bullets in enumerate(exp_bullets_list):
            rewritten = bullets
            hits_per_bullet = []
            for b in rewritten:
                hits = _compute_hits_for_bullet(
                    b, core_hard, core_soft, required_phrases
                )
                hits_per_bullet.append({"bullet": b, "hits": hits})
                for h in hits:
                    covered_all.add(_norm(h))
            selected.append(
                {
                    **exp_meta_list[k],
                    "bullets": rewritten,
                    "hits_per_bullet": hits_per_bullet,
                }
            )

        gaps = [req for req in core_hard if _norm(req) not in covered_all]
        return TailorBulletsOut(
            selected_experiences=selected,
            keywords_covered=sorted(list(covered_all)),
            gaps=gaps,
            summary=summary_original,
            cover_letter="",
        )
    # Apply summary (clamp)
    tailored_summary = ai.get("summary") or summary_original
    print("cover letter+++++++++++++++", ai.get("cover_letter"))
    user_name = db.query(User).filter(User.id == payload.user_id).first()
    tailored_cover_letter = (
        re.sub(
            r"\n{1,2}\[Your Name\]",
            f"\n{user_name.first_name}",
            (ai.get("cover_letter") or "").strip(),
        )
        if payload.include_cover_letter
        else ""
    )
    print("cover letter-------------", tailored_cover_letter)
    # Apply bullet rewrites deterministically (same count, same order per exp)
    exp_rewrites = {
        int(x.get("exp_index")): (x.get("rewrites") or [])
        for x in (ai.get("experiences") or [])
    }

    covered_all: Set[str] = set()
    selected: List[Dict[str, Any]] = []

    for exp_idx, orig_bullets in enumerate(exp_bullets_list):
        rewrites = exp_rewrites.get(exp_idx, [])
        by_source = {int(r.get("source_index", -1)): r for r in rewrites}

        rewritten_bullets: List[str] = []
        for j, orig in enumerate(orig_bullets):
            rw = str((by_source.get(j) or {}).get("rewritten") or orig).strip() or orig
            rewritten_bullets.append(rw)

        # Compute hits OUTSIDE AI (your requirement)
        hits_per_bullet = []
        for b in rewritten_bullets:
            hits = _compute_hits_for_bullet(b, core_hard, core_soft, required_phrases)
            hits_per_bullet.append({"bullet": b, "hits": hits})
            for h in hits:
                covered_all.add(_norm(h))

        selected.append(
            {
                **exp_meta_list[exp_idx],
                "bullets": rewritten_bullets,
                "hits_per_bullet": hits_per_bullet,
            }
        )

    gaps = [req for req in core_hard if _norm(req) not in covered_all]

    return TailorBulletsOut(
        selected_experiences=selected,
        keywords_covered=sorted(list(covered_all)),
        gaps=gaps,
        summary=tailored_summary,
        cover_letter=tailored_cover_letter,
    )


# ---------------------------
# Export tailored docx (summary + bullets)
# ---------------------------


class ExportTailoredDocxIn(BaseModel):
    user_id: str
    jd_key_id: int
    bullets_per_role: int = Field(default=5, ge=1, le=10)
    max_roles: int = Field(default=4, ge=1, le=10)
    export_format: str = Field(default="docx", description="docx | pdf | both")
    include_cover_letter: bool = False
    cover_letter_instructions: str = ""


@router.post("/v1/resume/export-tailored-docx")
def export_tailored_docx(
    payload: ExportTailoredDocxIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    _check_access(db, principal, payload.user_id)

    br = db.query(BaseResume).filter(BaseResume.user_id == payload.user_id).first()
    if not br:
        print("br in export+++++++++++++++++")
        raise HTTPException(status_code=404, detail="Base resume not found")
    resume = _load_base_resume_json(br)
    sf = (
        db.query(StoredFile)
        .filter(
            StoredFile.user_id == payload.user_id,
            StoredFile.application_id == "base",
            StoredFile.kind == "base_resume_docx",
        )
        .order_by(StoredFile.created_at.desc())
        .first()
    )
    if not sf:
        print("sf+++++++++++++++++")
        raise HTTPException(
            status_code=404,
            detail="Base resume DOCX not uploaded yet. Use PUT /v1/users/{user_id}/base-resume-docx",
        )

    try:
        # docx_bytes = open(sf.path, "rb").read()
        resp = requests.get(sf.path, timeout=30)
        resp.raise_for_status()
        docx_bytes = resp.content

    except Exception:
        raise HTTPException(
            status_code=500, detail="Failed to read stored base resume docx"
        )

    tailored = tailor_bullets(
        TailorBulletsIn(
            user_id=payload.user_id,
            jd_key_id=payload.jd_key_id,
            bullets_per_role=payload.bullets_per_role,
            max_roles=payload.max_roles,
            include_cover_letter=payload.include_cover_letter,
            cover_letter_instructions=payload.cover_letter_instructions,
        ),
        db=db,
        principal=principal,
    )

    # Replace summary first (if indices exist in stored resume JSON)
    summary_idxs = resume.get("summary_para_idxs") or []
    if summary_idxs and (tailored.summary or "").strip():
        docx_bytes = replace_summary_in_docx(docx_bytes, summary_idxs, tailored.summary)

    # Replace bullets
    bullet_blocks = resume.get("experiences") or []
    new_by_block: Dict[int, List[str]] = {}
    for i, exp in enumerate(tailored.selected_experiences):
        new_by_block[i] = exp.get("bullets") or []

    out_bytes = replace_bullets_in_docx(docx_bytes, bullet_blocks, new_by_block)

    # Optional PDF export
    # pdf_bytes = docx_bytes_to_pdf_bytes(out_bytes)
    pdf_bytes = out_bytes

    docx_b64 = base64.b64encode(out_bytes).decode("utf-8")
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    fmt = (payload.export_format or "docx").lower().strip()
    if fmt not in ("docx", "pdf", "both"):
        raise HTTPException(
            status_code=400, detail="export_format must be one of: docx, pdf, both"
        )
    print("cover letter+++++++++++++++++", tailored.cover_letter)
    # If both, return a zip (base64)
    if fmt == "both":
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("resume.docx", out_bytes)
            z.writestr("resume.pdf", pdf_bytes)
            if (tailored.cover_letter or "").strip():
                z.writestr("cover_letter.txt", tailored.cover_letter.strip() + "\n")
        zip_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return {
            "ok": True,
            "bundle_zip_base64": zip_b64,
            "bundle_filenames": ["resume.docx", "resume.pdf"]
            + (["cover_letter.txt"] if (tailored.cover_letter or "").strip() else []),
            "template_source": sf.filename,
            "summary": tailored.summary,
            "cover_letter": tailored.cover_letter,
            "selected_experiences": tailored.selected_experiences,
            "gaps": tailored.gaps,
        }

    if fmt == "pdf":
        return {
            "ok": True,
            "resume_pdf_base64": pdf_b64,
            "template_source": sf.filename,
            "summary": tailored.summary,
            "cover_letter": tailored.cover_letter,
            "selected_experiences": tailored.selected_experiences,
            "gaps": tailored.gaps,
        }

    # default: docx
    return {
        "ok": True,
        "resume_docx_base64": docx_b64,
        "template_source": sf.filename,
        "summary": tailored.summary,
        "cover_letter": tailored.cover_letter,
        "selected_experiences": tailored.selected_experiences,
        "gaps": tailored.gaps,
    }
