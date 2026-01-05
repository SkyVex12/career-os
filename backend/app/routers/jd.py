from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import Principal, get_db, get_principal
from ..models import AdminUser, JDKeyInfo
from ..ai import call_openai_json, build_prompt_compress_jd

router = APIRouter(prefix="/v1", tags=["jd"])


class JDKeysIn(BaseModel):
    user_id: str = Field(..., description="Owner of the application/resume context.")
    url: Optional[str] = Field(None, description="Job posting URL (optional).")
    jd_text: str = Field(
        ..., min_length=1, description="Job description text (full or partial)."
    )


def _ensure_access(db: Session, principal: Principal, user_id: str) -> None:
    if principal.type == "user":
        if principal.id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        return
    ok = (
        db.query(AdminUser)
        .filter(AdminUser.admin_id == principal.id, AdminUser.user_id == user_id)
        .first()
    )
    if not ok:
        raise HTTPException(status_code=403, detail="Forbidden")


def _norm_url(url: str) -> str:
    return (url or "").strip()


def _norm_text(s: str) -> str:
    x = (s or "").strip().lower()
    x = x.replace("\r\n", "\n")
    x = re.sub(r"[\t\u00a0]+", " ", x)
    x = re.sub(r"[ ]{2,}", " ", x)
    boiler = [
        "equal opportunity employer",
        "e-verify",
        "accommodation",
        "applicants with disabilities",
        "all qualified applicants",
        "gender identity",
        "sexual orientation",
    ]
    for b in boiler:
        x = x.replace(b, "")
    x = re.sub(r"\n{3,}", "\n\n", x)
    return x.strip()


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _extract_keys(jd_text: str) -> Dict[str, Any]:
    compress_prompt = build_prompt_compress_jd(jd_text)
    ats_package = call_openai_json(compress_prompt)

    return json.loads(ats_package)


@router.post("/jd/keys")
def get_or_create_jd_keys(
    payload: JDKeysIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    _ensure_access(db, principal, payload.user_id)

    norm_text = _norm_text(payload.jd_text)
    text_hash = _sha256(norm_text)

    source_url = _norm_url(payload.url) if payload.url else None
    url_hash = _sha256(source_url.lower()) if source_url else None

    q = db.query(JDKeyInfo)

    cache = None
    if url_hash:
        cache = (
            q.filter(
                JDKeyInfo.url_hash == url_hash,
                JDKeyInfo.text_hash == text_hash,
            )
            .order_by(JDKeyInfo.created_at.desc())
            .first()
        )

    if not cache:
        cache = (
            q.filter(JDKeyInfo.text_hash == text_hash)
            .order_by(JDKeyInfo.created_at.desc())
            .first()
        )

    if cache:
        return {
            "cache_hit": True,
            "id": cache.id,
            "scope": "canonical",
            "source_url": cache.source_url,
            "keys": json.loads(cache.keys_json),
        }

    keys = _extract_keys(payload.jd_text)
    now = datetime.utcnow()
    row = JDKeyInfo(
        user_id=payload.user_id,
        source_url=source_url,
        url_hash=url_hash,
        text_hash=text_hash,
        scope="canonical",
        keys_json=json.dumps(keys, ensure_ascii=False),
        model="heuristic_v1",
        created_at=now,
    )
    db.add(row)
    db.flush()

    return {
        "cache_hit": False,
        "id": row.id,
        "scope": "canonical",
        "source_url": row.source_url,
        "keys": keys,
    }
