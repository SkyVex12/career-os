from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field

from ..auth import Principal, get_db, get_principal
from ..models import Application, AdminUser, Admin, User, StoredFile

router = APIRouter(prefix="/v1", tags=["applications"])


class ApplicationOut(BaseModel):
    id: str
    user_id: str
    company: str
    role: str
    url: str
    stage: str
    created_at: dt.datetime

    class Config:
        from_attributes = True


class ApplicationUpdateIn(BaseModel):
    stage: str = Field(..., min_length=1)


def _scoped_query(db: Session, principal: Principal):
    q = db.query(Application)
    if principal.type == "user":
        q = q.filter(Application.user_id == principal.id)
    else:
        q = q.join(AdminUser, AdminUser.user_id == Application.user_id).filter(
            AdminUser.admin_id == principal.id
        )
    return q


def _admin_can_access_user(db: Session, admin_id: str, user_id: str) -> bool:
    return (
        db.query(AdminUser)
        .filter(AdminUser.admin_id == admin_id, AdminUser.user_id == user_id)
        .first()
        is not None
    )


def _ensure_access(db: Session, principal: Principal, user_id: str) -> None:
    if principal.type == "user":
        if principal.id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        return
    # admin
    if not _admin_can_access_user(db, principal.id, user_id):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/applications/exists")
def exists_application(
    user_id: str,
    url: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    _ensure_access(db, principal, user_id)
    row = (
        db.query(Application)
        .filter(Application.user_id == user_id, Application.url == url)
        .order_by(Application.created_at.desc())
        .first()
    )
    if not row:
        return {"exists": False}
    return {
        "exists": True,
        "application": {
            "id": row.id,
            "user_id": row.user_id,
            "created_by": (
                db.get(Admin, row.admin_id).name
                if row.admin_id
                else db.get(User, row.user_id).name
            ),
            "company": row.company,
            "role": row.role,
            "stage": row.stage,
            "url": row.url,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        },
    }


@router.get("/applications/stats")
def applications_stats(
    principal: Principal = Depends(get_principal),
    user_id: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    qset = db.query(Application)
    if user_id:
        qset = qset.filter(Application.user_id == user_id)

    # ---- stage counts ----
    stage_rows = (
        qset.with_entities(
            func.lower(Application.stage).label("stage"),
            func.count(Application.id).label("cnt"),
        )
        .group_by(func.lower(Application.stage))
        .all()
    )
    stage_counts = {(r.stage or "applied"): int(r.cnt) for r in stage_rows}

    # Use UTC "now" (naive). This matches most setups where created_at is stored as UTC.
    now = datetime.utcnow()

    # ---- series config ----
    if days == 1:
        step = "hour"
        cutoff = now - timedelta(hours=23)
        py_keys = [
            (cutoff + timedelta(hours=i)).strftime("%Y-%m-%d %H:00") for i in range(24)
        ]
        sqlite_fmt = "%Y-%m-%d %H:00"
        pg_fmt = "YYYY-MM-DD HH24:00"
    else:
        step = "day"
        cutoff = now - timedelta(days=days - 1)
        py_keys = [(cutoff + timedelta(days=i)).date().isoformat() for i in range(days)]
        sqlite_fmt = "%Y-%m-%d"
        pg_fmt = "YYYY-MM-DD"

    # ---- build time expression as STRING (dialect-safe) ----
    dialect = db.get_bind().dialect.name  # "postgresql" or "sqlite" etc.

    if dialect == "postgresql":
        # Normalize to UTC text. Works well even if your DB/session timezone is not UTC.
        # If created_at is "timestamp without time zone" and already UTC, this is still fine.
        created_at_utc = func.timezone("UTC", Application.created_at)
        time_expr = func.to_char(created_at_utc, pg_fmt)
    else:
        # SQLite
        time_expr = func.strftime(sqlite_fmt, Application.created_at)
    rows = (
        qset.filter(Application.created_at >= cutoff)
        .with_entities(
            time_expr.label("t"),
            func.count(Application.id).label("cnt"),
        )
        .group_by(time_expr)
        .order_by(time_expr)
        .all()
    )

    # t is now a string key (same type as py_keys)
    day_map = {r.t: int(r.cnt) for r in rows}

    # ---- build series ----
    series = []
    if step == "hour":
        for k in py_keys:
            series.append({"time": k, "count": day_map.get(k, 0)})
    else:
        for k in py_keys:
            series.append({"day": k, "count": day_map.get(k, 0)})

    print("sample db keys:", list(day_map.keys()))
    print("sample py keys:", py_keys)
    total = int(sum(stage_counts.values()))
    interviews = int(stage_counts.get("interview", 0))
    offers = int(stage_counts.get("offer", 0))
    rejected = int(stage_counts.get("rejected", 0))
    applied = int(stage_counts.get("applied", 0))

    return {
        "total": total,
        "stage_counts": stage_counts,
        "series": series,
        "series_unit": step,
        "success_rate": offers / max(1, total),
        "interview_rate": interviews / max(1, total),
        "rejection_rate": rejected / max(1, total),
        "applied_count": applied,
        "interview_count": interviews,
        "offer_count": offers,
        "rejected_count": rejected,
    }


@router.get("/applications")
def list_applications(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    view_mode: str = Query("kanban", regex="^(kanban|paged)$"),
    stage: Optional[str] = None,
    user_id: Optional[str] = None,
    q: Optional[str] = None,
    dedupe: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    dialect = db.get_bind().dialect.name

    if dialect == "postgresql":
        user_ids_expr = func.string_agg(func.distinct(Application.user_id), ", ")
    else:
        user_ids_expr = func.group_concat(func.distinct(Application.user_id), ", ")

    user_ids_subq = (
        db.query(
            Application.company.label("company"),
            Application.role.label("role"),
            Application.url.label("url"),
            user_ids_expr.label("user_ids"),
        )
        .group_by(Application.company, Application.role, Application.url)
        .subquery("user_ids_agg")
    )

    query = db.query(Application, user_ids_subq.c.user_ids).join(
        user_ids_subq,
        (user_ids_subq.c.company == Application.company)
        & (user_ids_subq.c.role == Application.role)
        & (user_ids_subq.c.url == Application.url),
    )

    if principal.type == "user":
        query = query.filter(Application.user_id == principal.id)
    else:
        # admin sees all users they have, optionally scoped to one user
        query = query.join(AdminUser, AdminUser.user_id == Application.user_id).filter(
            AdminUser.admin_id == principal.id
        )
        if user_id and user_id != "u1":
            query = query.filter(Application.user_id == user_id)

    if stage:
        query = query.filter(Application.stage == stage)

    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            or_(
                Application.company.ilike(like),
                Application.role.ilike(like),
                Application.stage.ilike(like),
                Application.url.ilike(like),
                Application.source_site.ilike(like),
            )
        )

    if not dedupe:
        total = query.count()
        items = (
            query.order_by(Application.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
    else:
        # 1) aggregate user_ids per (company, role, url)
        user_ids_expr = func.string_agg(func.distinct(Application.user_id), ", ")

        agg = (
            query.with_entities(
                Application.company.label("company"),
                Application.role.label("role"),
                Application.url.label("url"),
                user_ids_expr.label("user_ids"),
            )
            .group_by(Application.company, Application.role, Application.url)
            .subquery("agg")
        )

        # 2) rank rows per (company, role, url) to pick 1 row (newest)
        rn = (
            func.row_number()
            .over(
                partition_by=(Application.company, Application.role, Application.url),
                order_by=(
                    Application.updated_at.desc(),
                    Application.created_at.desc(),
                    Application.id.desc(),
                ),
            )
            .label("rn")
        )

        ranked = query.with_entities(
            Application.id.label("id"),
            Application.user_id.label("user_id"),
            Application.admin_id.label("admin_id"),
            Application.company.label("company"),
            Application.role.label("role"),
            Application.url.label("url"),
            Application.source_site.label("source_site"),
            Application.stage.label("stage"),
            Application.created_at.label("created_at"),
            Application.updated_at.label("updated_at"),
            rn,
        ).subquery("ranked")

        # IMPORTANT: select columns explicitly (ranked.c.*), not `ranked` as an entity
        final_q = (
            db.query(
                ranked.c.id,
                ranked.c.user_id,
                ranked.c.admin_id,
                ranked.c.company,
                ranked.c.role,
                ranked.c.url,
                ranked.c.source_site,
                ranked.c.stage,
                ranked.c.created_at,
                ranked.c.updated_at,
                agg.c.user_ids.label("user_ids"),
            )
            .join(
                agg,
                (agg.c.company == ranked.c.company)
                & (agg.c.role == ranked.c.role)
                & (agg.c.url == ranked.c.url),
            )
            .filter(ranked.c.rn == 1)
        )

        total = db.query(func.count()).select_from(final_q.subquery()).scalar() or 0

        rows = (
            final_q.order_by(ranked.c.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        # Now rows are plain tuples with known positions/labels
        items = [
            {
                "id": r.id,
                "user_id": r.user_id,
                "admin_id": r.admin_id,
                "company": r.company,
                "role": r.role,
                "stage": r.stage,
                "url": r.url,
                "source_site": r.source_site,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "user_ids": r.user_ids,
            }
            for r in rows
        ]

    app_ids = (
        [app.id for (app, user_ids) in items]
        if not dedupe
        else [x["id"] for x in items]
    )
    file_map = {}  # (app_id, kind) -> StoredFile
    if app_ids:
        rows = (
            db.query(StoredFile)
            .filter(
                StoredFile.application_id.in_(app_ids),
                StoredFile.kind.in_(["resume_docx", "resume_pdf"]),
            )
            .order_by(StoredFile.created_at.desc())
            .all()
        )
        for f in rows:
            key = (f.application_id, f.kind)
            if key not in file_map:
                file_map[key] = f

    def to_dict(a: Application, user_ids: str | None = None):
        docx = file_map.get((a.id, "resume_docx"))
        pdf = file_map.get((a.id, "resume_pdf"))
        return {
            "id": a.id,
            "user_id": a.user_id,
            "admin_id": a.admin_id,
            "company": a.company,
            "role": a.role,
            "stage": a.stage,
            "url": a.url,
            "source_site": a.source_site,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            "user_ids": user_ids,  # <-- NEW (string)
            "resume_docx_file_id": docx.id if docx else None,
            "resume_pdf_file_id": pdf.id if pdf else None,
            "resume_version_id": (
                pdf.resume_version_id
                if pdf and getattr(pdf, "resume_version_id", None)
                else (docx.resume_version_id if docx else None)
            ),
            "resume_docx_download_url": docx.path if docx else None,
            "resume_pdf_download_url": pdf.path if pdf else None,
        }

    if not dedupe:
        out_items = [to_dict(a, user_ids) for (a, user_ids) in items]
    else:
        # Reuse the same resume-file enrichment logic by adapting to_dict OR inline:
        out_items = []
        for x in items:
            docx = file_map.get((x["id"], "resume_docx"))
            pdf = file_map.get((x["id"], "resume_pdf"))
            out_items.append(
                {
                    **x,
                    "created_at": (
                        x["created_at"].isoformat() if x["created_at"] else None
                    ),
                    "updated_at": (
                        x["updated_at"].isoformat() if x["updated_at"] else None
                    ),
                    "resume_docx_file_id": docx.id if docx else None,
                    "resume_pdf_file_id": pdf.id if pdf else None,
                    "resume_version_id": (
                        pdf.resume_version_id
                        if pdf and getattr(pdf, "resume_version_id", None)
                        else (docx.resume_version_id if docx else None)
                    ),
                    "resume_docx_download_url": docx.path if docx else None,
                    "resume_pdf_download_url": pdf.path if pdf else None,
                }
            )

    return {
        "items": out_items,
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get(
    "/applications/{app_id}",
    response_model=ApplicationOut,
)
def get_application(app_id: int, db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "Application not found")
    return a


@router.patch(
    "/applications/{app_id}",
    response_model=ApplicationOut,
)
def update_application(
    app_id: str, payload: ApplicationUpdateIn, db: Session = Depends(get_db)
):
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "Application not found")
    a.stage = payload.stage
    a.updated_at = datetime.now()
    print(f"Updating application {app_id} to stage {payload.stage} at {a.updated_at}")
    db.commit()
    db.refresh(a)
    return a
