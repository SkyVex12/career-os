from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, text, case
from datetime import datetime, timedelta, timezone, date as date_type
from pydantic import BaseModel, Field

from ..auth import Principal, get_db, get_principal
from ..models import Application, AdminUser, JobDescription, Admin, User, StoredFile

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
        .join(
            job_description := JobDescription,
            job_description.application_id == Application.id,
        )
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
            "source_site": row.source_site,
            "company": row.company,
            "role": row.role,
            "jd_text": row.job_description.jd_text,
            "stage": row.stage,
            "url": row.url,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        },
    }


DAY_BOUNDARY_HOUR_UTC = 19


def boundary_end_for_day_label(day_label: date_type) -> datetime:
    """
    day_label = YYYY-MM-DD shown on chart.
    Window is: (day_label - 1 day) 19:00 UTC  ->  day_label 19:00 UTC
    """
    return datetime(
        year=day_label.year,
        month=day_label.month,
        day=day_label.day,
        hour=DAY_BOUNDARY_HOUR_UTC,
        minute=0,
        second=0,
        microsecond=0,
        # tzinfo=timezone.utc,
    )


@router.get("/applications/stats")
def applications_stats(
    principal: "Principal" = Depends(get_principal),
    user_id: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    day: date_type | None = Query(default=None),  # used when days==1
    db: Session = Depends(get_db),
):
    # ---- base query (user-scoped) ----
    qset = db.query(Application)

    if user_id:
        qset = qset.filter(Application.user_id == user_id)
    else:
        qset = qset.filter(Application.user_id == principal.id)

    dialect = db.get_bind().dialect.name
    # now = datetime.now(timezone.utc)
    now = datetime.now()

    # ---- determine end_boundary (7 PM) ----
    if days == 1 and day is not None:
        end_boundary = boundary_end_for_day_label(day)
    else:
        end_boundary = now.replace(
            hour=DAY_BOUNDARY_HOUR_UTC, minute=0, second=0, microsecond=0
        )
        if now < end_boundary:
            end_boundary -= timedelta(days=1)

    # ---- determine window start and build series ----
    if days == 1:
        # Hourly series (last 24 hours inside selected 7PM window)
        start_ts = end_boundary - timedelta(hours=23)
        series_unit = "hour"

        py_keys = [
            (start_ts + timedelta(hours=i)).strftime("%Y-%m-%d %H:00")
            for i in range(24)
        ]

        if dialect == "postgresql":
            # bucket_expr = func.date_trunc(
            #     "hour", func.timezone("UTC", Application.created_at)
            # )
            bucket_expr = func.date_trunc("hour", Application.created_at)
            key_expr = func.to_char(bucket_expr, "YYYY-MM-DD HH24:00")
        else:
            key_expr = func.strftime("%Y-%m-%d %H:00", Application.created_at)

        # Filter query to the selected window
        window_q = qset.filter(
            Application.created_at >= (end_boundary - timedelta(days=1)),
            Application.created_at < end_boundary,
        )

        rows = (
            window_q.with_entities(
                key_expr.label("k"),
                func.count(Application.id).label("cnt"),
            )
            .group_by(key_expr)
            .order_by(key_expr)
            .all()
        )
        bucket_map = {r.k: int(r.cnt) for r in rows}
        series = [{"time": k, "count": bucket_map.get(k, 0)} for k in py_keys]

        window = {
            "start_utc": (end_boundary - timedelta(days=1)).isoformat(),
            "end_utc": end_boundary.isoformat(),
        }

    else:
        # Daily series (custom 7PM day buckets)
        start_ts = end_boundary - timedelta(days=days - 1)
        series_unit = "day_7pm_to_7pm"

        py_keys = [
            (start_ts + timedelta(days=i)).date().isoformat() for i in range(days)
        ]

        if dialect == "postgresql":
            shifted = func.timezone(
                "UTC",
                Application.created_at
                - text(f"interval '{DAY_BOUNDARY_HOUR_UTC} hours'"),
            )
            key_expr = func.to_char(func.date_trunc("day", shifted), "YYYY-MM-DD")
        else:
            key_expr = func.strftime(
                "%Y-%m-%d",
                Application.created_at,
                f"-{DAY_BOUNDARY_HOUR_UTC} hours",
            )

        # Filter query to the selected window
        window_q = qset.filter(
            Application.created_at >= (end_boundary - timedelta(days=days)),
            Application.created_at < end_boundary,
        )

        rows = (
            window_q.with_entities(
                key_expr.label("k"),
                func.count(Application.id).label("cnt"),
            )
            .group_by(key_expr)
            .order_by(key_expr)
            .all()
        )
        bucket_map = {r.k: int(r.cnt) for r in rows}
        series = [{"day": k, "count": bucket_map.get(k, 0)} for k in py_keys]

        window = {
            "start_utc": (end_boundary - timedelta(days=days)).isoformat(),
            "end_utc": end_boundary.isoformat(),
        }

    # ✅ IMPORTANT: stage counts must use the SAME window_q
    stage_rows = (
        window_q.with_entities(
            func.lower(Application.stage).label("stage"),
            func.count(Application.id).label("cnt"),
        )
        .group_by(func.lower(Application.stage))
        .all()
    )
    stage_counts = {(r.stage or "applied"): int(r.cnt) for r in stage_rows}

    # ---- summary metrics (window-scoped) ----
    total = int(sum(stage_counts.values()))
    interviews = int(stage_counts.get("interview", 0))
    offers = int(stage_counts.get("offer", 0))
    rejected = int(stage_counts.get("rejected", 0))
    applied = int(stage_counts.get("applied", 0))

    # ==========================================================
    # ✅ NEW: Per-source-site success stats (window-scoped)
    # ==========================================================
    stage_l = func.lower(Application.stage)

    applied_flag = case((stage_l == "applied", 1), else_=0)
    interview_flag = case((stage_l == "interview", 1), else_=0)
    offer_flag = case((stage_l == "offer", 1), else_=0)
    rejected_flag = case((stage_l == "rejected", 1), else_=0)

    # reached interview == interview OR offer (you can expand later)
    reached_interview_flag = case(
        (stage_l.in_(["interview", "offer"]), 1),
        else_=0,
    )

    # success == offer
    success_flag = offer_flag

    # normalize source_site
    source_expr = func.coalesce(
        func.nullif(func.trim(Application.source_site), ""),
        "unknown",
    )
    source_expr = func.lower(source_expr)

    source_rows = (
        window_q.with_entities(
            source_expr.label("source_site"),
            func.count(Application.id).label("total"),
            func.sum(applied_flag).label("applied"),
            func.sum(interview_flag).label("interview"),
            func.sum(offer_flag).label("offer"),
            func.sum(rejected_flag).label("rejected"),
            func.sum(reached_interview_flag).label("reached_interview"),
            func.sum(success_flag).label("success"),
        )
        .group_by(source_expr)
        .order_by(func.count(Application.id).desc())
        .all()
    )

    source_site_stats = []
    for r in source_rows:
        total_s = int(r.total or 0)
        reached_interview = int(r.reached_interview or 0)
        success = int(r.success or 0)

        source_site_stats.append(
            {
                "source_site": r.source_site,
                "total": total_s,
                "applied_count": int(r.applied or 0),
                "interview_count": int(r.interview or 0),
                "offer_count": int(r.offer or 0),
                "rejected_count": int(r.rejected or 0),
                "interview_rate": reached_interview / max(1, total_s),
                "success_rate": success / max(1, total_s),
            }
        )

    source_site_stats.sort(
        key=lambda x: (x["interview_rate"], x["total"]),
        reverse=True,
    )

    return {
        "total": total,
        "stage_counts": stage_counts,
        "series": series,
        "series_unit": "hour" if series_unit == "hour" else "day",
        "window": window,
        "success_rate": offers / max(1, total),
        "interview_rate": interviews / max(1, total),
        "rejection_rate": rejected / max(1, total),
        "applied_count": applied,
        "interview_count": interviews,
        "offer_count": offers,
        "rejected_count": rejected,
        # ✅ NEW
        "source_site_stats": source_site_stats,
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
