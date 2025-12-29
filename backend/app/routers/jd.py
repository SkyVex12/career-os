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

router = APIRouter(prefix="/v1", tags=["jd"])


class JDKeysIn(BaseModel):
    user_id: str = Field(..., description="Owner of the application/resume context.")
    source_url: Optional[str] = Field(None, description="Job posting URL (optional).")
    jd_text: str = Field(
        ..., min_length=1, description="Job description text (full or partial)."
    )
    scope: str = Field("fragment", pattern="^(canonical|fragment)$")


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


_TECH = [
    "python",
    "javascript",
    "typescript",
    "react",
    "next.js",
    "node",
    "fastapi",
    "django",
    "flask",
    "aws",
    "gcp",
    "azure",
    "kubernetes",
    "docker",
    "terraform",
    "postgres",
    "mysql",
    "mongodb",
    "redis",
    "graphql",
    "rest",
    "microservices",
    "ci/cd",
    "github actions",
    "gitlab",
    "spark",
    "airflow",
    "etl",
    "machine learning",
    "nlp",
    "llm",
    "openai",
    "pandas",
    "numpy",
    "pytorch",
    "tensorflow",
    "java",
    "go",
    "golang",
    "c#",
    "php",
    "laravel",
    "spring",
    "dotnet",
    "kafka",
    "rabbitmq",
    "snowflake",
    "databricks",
    "bigquery",
]


def _extract_keys(jd_text: str) -> Dict[str, Any]:
    """Cheap, deterministic extractor to reduce OpenAI usage."""
    raw = jd_text.strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    head = " ".join(lines[:8])

    job_title = ""
    m = re.search(r"(role|position|title)\s*:\s*([^\n]+)", raw, re.I)
    if m:
        job_title = m.group(2).strip()[:120]
    elif lines:
        job_title = lines[0][:120]

    bullets = []
    for ln in lines:
        if re.match(r"^[-•\*\u2022]\s+", ln):
            bullets.append(re.sub(r"^[-•\*\u2022]\s+", "", ln).strip())
    if not bullets:
        bullets = [ln for ln in lines[1:20] if len(ln) > 30][:10]
    responsibilities = bullets[:12]

    txt_low = raw.lower()

    tech_stack = []
    for k in _TECH:
        if k in txt_low:
            tech_stack.append(k)
    tech_stack = sorted(set(tech_stack))

    must = []
    nice = []
    must_section = re.search(
        r"(requirements|qualifications|what you bring|must have)([\s\S]{0,2500})",
        raw,
        re.I,
    )
    pref_section = re.search(
        r"(preferred|nice to have|bonus)([\s\S]{0,2500})", raw, re.I
    )
    if must_section:
        sec = must_section.group(2).lower()
        for k in tech_stack:
            if k in sec:
                must.append(k)
    if pref_section:
        sec = pref_section.group(2).lower()
        for k in tech_stack:
            if k in sec:
                nice.append(k)

    keywords = list(dict.fromkeys(tech_stack))[:30]

    location = ""
    loc = re.search(r"(location|based in)\s*:\s*([^\n]+)", raw, re.I)
    if loc:
        location = loc.group(2).strip()[:80]

    seniority = ""
    if re.search(r"\bsenior\b", head, re.I):
        seniority = "senior"
    elif re.search(r"\bjunior\b|\bentry\b", head, re.I):
        seniority = "junior"
    elif re.search(r"\bstaff\b", head, re.I):
        seniority = "staff"
    elif re.search(r"\bprincipal\b", head, re.I):
        seniority = "principal"

    return {
        "job_title": job_title,
        "seniority": seniority,
        "location": location,
        "must_have_skills": sorted(set(must)),
        "nice_to_have_skills": sorted(set(nice)),
        "responsibilities": responsibilities,
        "keywords": keywords,
        "tech_stack": tech_stack,
        "domain": "",
    }


@router.post("/jd/keys")
def get_or_create_jd_keys(
    payload: JDKeysIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    _ensure_access(db, principal, payload.user_id)

    norm_text = _norm_text(payload.jd_text)
    text_hash = _sha256(norm_text)

    source_url = _norm_url(payload.source_url) if payload.source_url else None
    url_hash = _sha256(source_url.lower()) if source_url else None

    q = db.query(JDKeyInfo).filter(JDKeyInfo.user_id == payload.user_id)

    cache = None
    if url_hash:
        cache = (
            q.filter(
                JDKeyInfo.url_hash == url_hash,
                JDKeyInfo.scope == payload.scope,
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
            "scope": cache.scope,
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
        scope=payload.scope,
        keys_json=json.dumps(keys, ensure_ascii=False),
        model="heuristic_v1",
        created_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "cache_hit": False,
        "id": row.id,
        "scope": row.scope,
        "source_url": row.source_url,
        "keys": keys,
    }
