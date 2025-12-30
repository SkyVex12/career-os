from __future__ import annotations

import base64
import json
import re
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import Principal, get_principal
from ..db import SessionLocal
from ..models import AdminUser, BaseResume, JDKeyInfo, StoredFile
from ..resume_docx import replace_bullets_in_docx
from ..ai import tailor_rewrite_experience

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
    """Token-intersection match (same approach as your earlier scorer)."""
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
    """
    content_text is expected to be JSON; fallback: treat as plain text and extract bullet blocks.
    """
    txt = br.content_text or ""
    try:
        obj = json.loads(txt)
        if isinstance(obj, dict) and ("experiences" in obj):
            return obj
    except Exception:
        pass

    bullets: List[str] = []
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith(("•", "-", "*", "●")):
            bullets.append(s.lstrip("●•-* ").strip())

    return {
        "schema": "resume_json_fallback_v1",
        "experiences": [{"header": "", "bullets": bullets, "bullet_para_idxs": []}],
    }


# ---------------------------
# API Models
# ---------------------------


class TailorBulletsIn(BaseModel):
    user_id: str
    jd_key_id: int
    bullets_per_role: int = Field(default=5, ge=1, le=10)  # kept for compatibility
    max_roles: int = Field(default=4, ge=1, le=10)


class TailorBulletsOut(BaseModel):
    selected_experiences: List[Dict[str, Any]]
    keywords_covered: List[str]
    gaps: List[str]


# ---------------------------
# Endpoint: tailor bullets (AI rewrite; hits+gaps computed server-side)
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
        raise HTTPException(status_code=404, detail="Base resume not found")

    jd = db.get(JDKeyInfo, payload.jd_key_id)
    if not jd:
        raise HTTPException(status_code=404, detail="JD keys not found")

    resume = _load_base_resume_json(br)
    exps = resume.get("experiences") or []
    if not isinstance(exps, list) or not exps:
        raise HTTPException(
            status_code=400, detail="Base resume JSON has no experiences"
        )

    try:
        jd_keys = json.loads(jd.keys_json or "{}")
        if not isinstance(jd_keys, dict):
            jd_keys = {}
    except Exception:
        jd_keys = {}

    core_hard = _dedupe_keep_order(jd_keys.get("core_hard") or [])
    core_soft = _dedupe_keep_order(jd_keys.get("core_soft") or [])
    required_phrases = _dedupe_keep_order(jd_keys.get("required_phrases") or [])

    # Token pools for verification
    all_resume_bullets: List[str] = []
    for exp in exps:
        for b in exp.get("bullets") or []:
            all_resume_bullets.append(str(b))

    covered_all: Set[str] = set()
    selected: List[Dict[str, Any]] = []

    for exp in exps[: payload.max_roles]:
        bullets = [str(b).strip() for b in (exp.get("bullets") or []) if str(b).strip()]
        if not bullets:
            continue

        # AI rewrite
        try:
            ai = tailor_rewrite_experience(
                exp_bullets=bullets,
                core_hard=core_hard,
                core_soft=core_soft,
                required_phrases=required_phrases,
            )
        except Exception as e:
            print("AI error:", e)
            rewritten_bullets = bullets[:]  # same count
            hits_per_bullet: List[Dict[str, Any]] = []
            for b in rewritten_bullets:
                hits = _compute_hits_for_bullet(
                    b, core_hard, core_soft, required_phrases
                )
                hits_per_bullet.append({"bullet": b, "hits": hits})
                for h in hits:
                    covered_all.add(_norm(h))

            selected.append(
                {"bullets": rewritten_bullets, "hits_per_bullet": hits_per_bullet}
            )
            continue

        items = ai.get("rewrites") or []

        # Ensure same length + correct ordering (fail closed)
        items_by_idx = {int(it.get("source_index", -1)): it for it in items}
        ordered_items: List[Dict[str, Any]] = []
        for i, orig_b in enumerate(bullets):
            it = items_by_idx.get(i)
            if not it:
                ordered_items.append(
                    {"source_index": i, "original": orig_b, "rewritten": orig_b}
                )
            else:
                ordered_items.append(
                    {
                        "source_index": i,
                        "original": str(it.get("original") or orig_b).strip() or orig_b,
                        "rewritten": str(it.get("rewritten") or orig_b).strip()
                        or orig_b,
                    }
                )

        rewritten_bullets = [i["rewritten"] for i in ordered_items]
        # Compute hits OUTSIDE AI (using final rewritten bullets)
        hits_per_bullet: List[Dict[str, Any]] = []
        for b in rewritten_bullets:
            hits = _compute_hits_for_bullet(b, core_hard, core_soft, required_phrases)
            hits_per_bullet.append({"bullet": b, "hits": hits})
            for h in hits:
                covered_all.add(_norm(h))

        selected.append(
            {"bullets": rewritten_bullets, "hits_per_bullet": hits_per_bullet}
        )

    # Gaps computed OUTSIDE AI (based on final coverage)
    gaps: List[str] = []
    for req in core_hard:
        if _norm(req) not in covered_all:
            gaps.append(req)

    return TailorBulletsOut(
        selected_experiences=selected,
        keywords_covered=sorted(list(covered_all)),
        gaps=gaps,
    )


# ---------------------------
# Endpoint: export tailored docx
# ---------------------------


class ExportTailoredDocxIn(BaseModel):
    user_id: str
    jd_key_id: int
    bullets_per_role: int = Field(default=5, ge=1, le=10)  # kept for compatibility
    max_roles: int = Field(default=4, ge=1, le=10)


@router.post("/v1/resume/export-tailored-docx")
def export_tailored_docx(
    payload: ExportTailoredDocxIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """Export a DOCX using the ORIGINAL uploaded resume as the template."""
    _check_access(db, principal, payload.user_id)

    br = db.query(BaseResume).filter(BaseResume.user_id == payload.user_id).first()
    if not br:
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
        raise HTTPException(
            status_code=404,
            detail="Base resume DOCX not uploaded yet. Use PUT /v1/users/{user_id}/base-resume-docx",
        )

    try:
        docx_bytes = open(sf.path, "rb").read()
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
        ),
        db=db,
        principal=principal,
    )
    bullet_blocks = resume.get("experiences") or []
    new_by_block: Dict[int, List[str]] = {}
    for i, exp in enumerate(tailored.selected_experiences):
        new_by_block[i] = exp.get("bullets") or []
    out_bytes = replace_bullets_in_docx(docx_bytes, bullet_blocks, new_by_block)
    b64 = base64.b64encode(out_bytes).decode("utf-8")

    return {
        "ok": True,
        "resume_docx_base64": b64,
        "template_source": sf.filename,
        "selected_experiences": tailored.selected_experiences,
        "gaps": tailored.gaps,
    }
