"""JSON API request endpoints for the Vue SPA."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Attachment, HelpRequest, LibraryPaper, PointTransaction, Report, User
from ...pdf_redact import safe_desensitize
from ...points import REASON_HELP_ACCEPTED, REASON_PUBLISH_DEDUCT, InsufficientPoints, adjust_points
from ...runtime_config import as_bool, as_int, get_setting
from ...security import current_user, require_csrf_header, require_login
from ...services import (
    UPLOADS_DIR,
    complete_request,
    force_close_request,
    latest_attachment,
    library_files,
    reject_upload,
)
from ...settings import settings
from ...timekit import CN_TZ, humanize_remaining, now_utc_naive

logger = logging.getLogger("lit-share.api.requests")
router = APIRouter(prefix="/api/v1/requests", tags=["api-requests"])

BOUNTY_OPTIONS = [10, 20, 30, 50]
PAGE_SIZE = 20
CURRENT_YEAR = datetime.now(CN_TZ).year
MIN_YEAR = 1800
MAX_YEAR = CURRENT_YEAR + 1


def _normalize_journal(raw: str) -> str:
    return " ".join(raw.split()).lower()


def _cn_month_start_utc() -> datetime:
    now_cn = datetime.now(CN_TZ)
    month_start_cn = now_cn.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return month_start_cn.astimezone(timezone.utc).replace(tzinfo=None)


def _journal_quota_used_this_month(db: Session, user_id: int, journal_norm: str) -> int:
    if not journal_norm:
        return 0
    return db.scalar(
        select(func.count(HelpRequest.id)).where(
            HelpRequest.requester_id == user_id,
            func.lower(HelpRequest.journal) == journal_norm,
            HelpRequest.created_at >= _cn_month_start_utc(),
        )
    ) or 0


def _active_request_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count(HelpRequest.id)).where(
            HelpRequest.requester_id == user_id,
            HelpRequest.status.in_(("open", "claimed", "awaiting_confirm")),
        )
    ) or 0


def _req_to_json(req: HelpRequest, requester_nick: str, helper_nick: str | None = None,
                 viewer: User | None = None, db: Session | None = None) -> dict:
    """Serialize a HelpRequest to JSON with role-aware fields."""
    data = {
        "id": req.id,
        "requester_id": req.requester_id,
        "requester_nickname": requester_nick,
        "title": req.title,
        "authors": req.authors,
        "journal": req.journal,
        "year": req.year,
        "extra": req.extra,
        "bounty": req.bounty,
        "status": req.status,
        "claimed_by": req.claimed_by,
        "helper_nickname": helper_nick,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "claimed_at": req.claimed_at.isoformat() if req.claimed_at else None,
        "uploaded_at": req.uploaded_at.isoformat() if req.uploaded_at else None,
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
    }

    # Time remaining
    if req.status == "open":
        data["time_remaining"] = humanize_remaining(req.request_deadline)
    elif req.status == "awaiting_confirm":
        data["time_remaining"] = humanize_remaining(req.confirm_deadline)
    else:
        data["time_remaining"] = None

    # Role-aware fields
    if viewer and db:
        data["viewer_role"] = "owner" if viewer.id == req.requester_id else (
            "helper" if viewer.id == (req.claimed_by or 0) else "visitor"
        )
        # Report eligibility
        if viewer.id != req.requester_id and viewer.id != (req.claimed_by or 0):
            min_helps = get_setting(db, "REPORTER_MIN_HELPS", settings.REPORTER_MIN_HELPS, cast=as_int)
            helps_count = db.scalar(
                select(func.count(PointTransaction.id)).where(
                    PointTransaction.user_id == viewer.id,
                    PointTransaction.reason == REASON_HELP_ACCEPTED,
                )
            ) or 0
            data["can_report"] = helps_count >= min_helps
            if data["can_report"]:
                data["already_reported"] = db.scalar(
                    select(func.count(Report.id)).where(
                        Report.request_id == req.id, Report.reporter_id == viewer.id,
                    )
                ) > 0
            else:
                data["already_reported"] = False
        else:
            data["can_report"] = False
            data["already_reported"] = False
    else:
        data["viewer_role"] = "visitor"
        data["can_report"] = False
        data["already_reported"] = False

    return data


class CreateRequestBody(BaseModel):
    title: str
    authors: str
    journal: str = ""
    year: int
    extra: str = ""
    bounty: int


class RejectBody(BaseModel):
    reason: str = ""


class ReportBody(BaseModel):
    reason: str


# ---------------------------------------------------------------------------
# Lobby
# ---------------------------------------------------------------------------

@router.get("")
def lobby(
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    total = db.scalar(
        select(func.count(HelpRequest.id)).where(HelpRequest.status == "open")
    ) or 0
    offset = (page - 1) * PAGE_SIZE
    rows = db.execute(
        select(HelpRequest, User.nickname)
        .join(User, User.id == HelpRequest.requester_id)
        .where(HelpRequest.status == "open")
        .order_by(desc(HelpRequest.created_at))
        .offset(offset).limit(PAGE_SIZE)
    ).all()

    items = [
        {
            "id": req.id,
            "title": req.title,
            "authors": req.authors,
            "journal": req.journal,
            "year": req.year,
            "bounty": req.bounty,
            "status": req.status,
            "requester_nickname": nick,
            "created_at": req.created_at.isoformat(),
            "time_remaining": humanize_remaining(req.request_deadline),
        }
        for req, nick in rows
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "total_pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
    }


# ---------------------------------------------------------------------------
# New request info (pre-fill data)
# ---------------------------------------------------------------------------

@router.get("/new-info")
def new_info(
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    timeout_days = get_setting(db, "REQUEST_TIMEOUT_DAYS", settings.REQUEST_TIMEOUT_DAYS, cast=as_int)
    active_limit = get_setting(db, "MAX_ACTIVE_REQUESTS", settings.MAX_ACTIVE_REQUESTS, cast=as_int)
    active_count = _active_request_count(db, user.id)
    return {
        "points": user.points,
        "active_count": active_count,
        "max_active": active_limit,
        "timeout_days": timeout_days,
        "bounty_options": BOUNTY_OPTIONS,
    }


# ---------------------------------------------------------------------------
# Create request
# ---------------------------------------------------------------------------

@router.post("")
def create_request(
    body: CreateRequestBody,
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    title = body.title.strip()
    authors = body.authors.strip()
    journal = body.journal.strip()
    extra = body.extra.strip()

    timeout_days = get_setting(db, "REQUEST_TIMEOUT_DAYS", settings.REQUEST_TIMEOUT_DAYS, cast=as_int)
    journal_limit = get_setting(db, "SAME_JOURNAL_MONTHLY_LIMIT", settings.SAME_JOURNAL_MONTHLY_LIMIT, cast=as_int)
    active_limit = get_setting(db, "MAX_ACTIVE_REQUESTS", settings.MAX_ACTIVE_REQUESTS, cast=as_int)
    active_count = _active_request_count(db, user.id)

    if not title:
        return JSONResponse({"detail": "标题不能为空"}, status_code=400)
    if len(title) > 500:
        return JSONResponse({"detail": "标题过长（≤500 字）"}, status_code=400)
    if not authors:
        return JSONResponse({"detail": "作者不能为空"}, status_code=400)
    if len(authors) > 500:
        return JSONResponse({"detail": "作者过长（≤500 字）"}, status_code=400)
    if len(journal) > 300:
        return JSONResponse({"detail": "期刊名过长（≤300 字）"}, status_code=400)
    if not (MIN_YEAR <= body.year <= MAX_YEAR):
        return JSONResponse({"detail": f"年份需在 {MIN_YEAR}–{MAX_YEAR} 之间"}, status_code=400)
    if body.bounty not in BOUNTY_OPTIONS:
        return JSONResponse({"detail": "悬赏积分必须是 10/20/30/50 之一"}, status_code=400)
    if active_count >= active_limit:
        return JSONResponse({"detail": f"已达到进行中求助上限 {active_limit} 条"}, status_code=400)

    journal_norm = _normalize_journal(journal)
    if journal_norm:
        used = _journal_quota_used_this_month(db, user.id, journal_norm)
        if used >= journal_limit:
            return JSONResponse({"detail": f"本月在「{journal}」已达单期刊月度上限 {journal_limit} 篇"}, status_code=400)

    deadline = now_utc_naive() + timedelta(days=timeout_days)

    new_req = HelpRequest(
        requester_id=user.id,
        title=title, authors=authors, journal=journal, year=body.year, extra=extra,
        bounty=body.bounty, status="open",
        request_deadline=deadline,
    )
    db.add(new_req)
    db.flush()

    try:
        adjust_points(
            db, user.id, -body.bounty, REASON_PUBLISH_DEDUCT,
            ref_request_id=new_req.id, note=f"bounty for #{new_req.id}",
        )
    except InsufficientPoints:
        db.rollback()
        return JSONResponse({"detail": f"积分不足（需 {body.bounty}，当前 {user.points}）"}, status_code=400)

    db.commit()
    return {"id": new_req.id, "status": "open"}


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@router.get("/{req_id}")
def detail(
    req_id: int,
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(current_user),
):
    row = db.execute(
        select(HelpRequest, User.nickname)
        .join(User, User.id == HelpRequest.requester_id)
        .where(HelpRequest.id == req_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404)

    req, requester_nick = row
    helper_nick = None
    if req.claimed_by:
        helper_nick = db.scalar(select(User.nickname).where(User.id == req.claimed_by))

    return _req_to_json(req, requester_nick, helper_nick, viewer, db)


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------

@router.post("/{req_id}/claim")
def claim(
    req_id: int,
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=404)
    if req.status != "open":
        return JSONResponse({"detail": "当前状态不可认领"}, status_code=400)
    if req.requester_id == user.id:
        return JSONResponse({"detail": "不能应助自己发布的求助"}, status_code=400)
    req.status = "claimed"
    req.claimed_by = user.id
    req.claimed_at = now_utc_naive()
    db.commit()
    return {"ok": True, "status": "claimed"}


@router.post("/{req_id}/release")
def release(
    req_id: int,
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=404)
    if req.status != "claimed":
        return JSONResponse({"detail": "已上传或已完结的求助不能放弃"}, status_code=400)
    if req.claimed_by != user.id:
        return JSONResponse({"detail": "只有应助者可以放弃"}, status_code=400)
    req.status = "open"
    req.claimed_by = None
    req.claimed_at = None
    db.commit()
    return {"ok": True, "status": "open"}


@router.post("/{req_id}/upload")
async def upload(
    req_id: int,
    pdf: UploadFile = File(...),
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=404)
    if req.status != "claimed":
        return JSONResponse({"detail": "当前状态不允许上传"}, status_code=400)
    if req.claimed_by != user.id:
        return JSONResponse({"detail": "只有当前应助者可以上传"}, status_code=400)

    max_mb = get_setting(db, "MAX_PDF_SIZE_MB", settings.MAX_PDF_SIZE_MB, cast=as_int)
    max_bytes = max_mb * 1024 * 1024

    contents = await pdf.read()
    if len(contents) == 0:
        return JSONResponse({"detail": "请选择一个 PDF 文件"}, status_code=400)
    if len(contents) > max_bytes:
        return JSONResponse({"detail": f"PDF 不能超过 {max_mb}MB"}, status_code=400)
    if len(contents) < 1024:
        return JSONResponse({"detail": "PDF 文件太小，不像有效内容"}, status_code=400)
    if contents[:5] != b"%PDF-":
        return JSONResponse({"detail": "不是有效的 PDF"}, status_code=400)

    ts = int(time.time())
    raw_path = UPLOADS_DIR / f"req{req.id}_h{user.id}_{ts}.pdf"
    raw_path.write_bytes(contents)

    sani_path = UPLOADS_DIR / f"req{req.id}_h{user.id}_{ts}.sanitized.pdf"
    stats = safe_desensitize(str(raw_path), str(sani_path))
    desensitized = bool(stats and sani_path.exists())

    db.add(Attachment(
        request_id=req.id,
        helper_id=user.id,
        original_path=str(raw_path),
        sanitized_path=str(sani_path) if desensitized else "",
        desensitized=desensitized,
        size_bytes=len(contents),
    ))

    confirm_hours = get_setting(db, "CONFIRM_WINDOW_HOURS", settings.CONFIRM_WINDOW_HOURS, cast=as_int)
    now = now_utc_naive()
    req.status = "awaiting_confirm"
    req.uploaded_at = now
    req.confirm_deadline = now + timedelta(hours=confirm_hours)
    db.commit()

    return {"ok": True, "status": "awaiting_confirm"}


@router.post("/{req_id}/confirm")
def confirm(
    req_id: int,
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=404)
    if req.requester_id != user.id:
        return JSONResponse({"detail": "只有求助者可以确认"}, status_code=400)
    if req.status != "awaiting_confirm":
        return JSONResponse({"detail": "当前状态不可确认"}, status_code=400)
    try:
        complete_request(db, req)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("confirm failed for req %d", req_id)
        return JSONResponse({"detail": f"确认失败: {e}"}, status_code=500)
    return {"ok": True, "status": "completed"}


@router.post("/{req_id}/reject")
def reject_req(
    req_id: int,
    body: RejectBody,
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=404)
    if req.requester_id != user.id:
        return JSONResponse({"detail": "只有求助者可以驳回"}, status_code=400)
    if req.status != "awaiting_confirm":
        return JSONResponse({"detail": "当前状态不可驳回"}, status_code=400)
    reject_upload(db, req, body.reason.strip()[:500])
    db.commit()
    return {"ok": True, "status": "open"}


@router.post("/{req_id}/report")
def report_req(
    req_id: int,
    body: ReportBody,
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=404)
    if req.requester_id == user.id:
        return JSONResponse({"detail": "不能举报自己发布的求助"}, status_code=400)
    reason = body.reason.strip()
    if not reason:
        return JSONResponse({"detail": "请填写举报原因"}, status_code=400)

    min_helps = get_setting(db, "REPORTER_MIN_HELPS", settings.REPORTER_MIN_HELPS, cast=as_int)
    helps_count = db.scalar(
        select(func.count(PointTransaction.id)).where(
            PointTransaction.user_id == user.id,
            PointTransaction.reason == REASON_HELP_ACCEPTED,
        )
    ) or 0
    if helps_count < min_helps:
        return JSONResponse({"detail": f"举报门槛：需累计应助 ≥ {min_helps} 次（你目前 {helps_count}）"}, status_code=400)

    already = db.scalar(
        select(func.count(Report.id)).where(
            Report.request_id == req.id, Report.reporter_id == user.id,
        )
    ) or 0
    if already:
        return JSONResponse({"detail": "你已举报过这条求助"}, status_code=400)

    db.add(Report(request_id=req.id, reporter_id=user.id, reason=reason[:255]))
    db.flush()

    threshold = get_setting(db, "REPORT_THRESHOLD", settings.REPORT_THRESHOLD, cast=as_int)
    distinct_reporters = db.scalar(
        select(func.count(func.distinct(Report.reporter_id))).where(Report.request_id == req.id)
    ) or 0

    auto_closed = False
    if distinct_reporters >= threshold and req.status not in ("closed", "expired", "completed"):
        force_close_request(db, req, note=f"自动关闭：举报达 {distinct_reporters}/{threshold} 次")
        auto_closed = True

    db.commit()
    message = "举报已提交" + ("，求助已自动关闭" if auto_closed else "")
    return {"ok": True, "message": message, "auto_closed": auto_closed}


@router.get("/{req_id}/download")
def download(
    req_id: int,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=404)

    want_sani = get_setting(db, "PDF_DESENSITIZE_ENABLED", settings.PDF_DESENSITIZE_ENABLED, cast=as_bool)
    file_path: Optional[Path] = None

    if req.status == "completed":
        if req.library_paper_id is None:
            raise HTTPException(status_code=500, detail="library_paper_missing")
        paper = db.get(LibraryPaper, req.library_paper_id)
        if paper is None:
            raise HTTPException(status_code=500, detail="library_paper_missing")
        orig, sani = library_files(paper)
        file_path = sani if (want_sani and sani.exists()) else orig
    elif req.status == "awaiting_confirm" and user.id in (req.requester_id, req.claimed_by or 0):
        att = latest_attachment(db, req.id)
        if att is None:
            raise HTTPException(status_code=404)
        if want_sani and att.sanitized_path and Path(att.sanitized_path).exists():
            file_path = Path(att.sanitized_path)
        else:
            file_path = Path(att.original_path)
    else:
        raise HTTPException(status_code=403)

    if file_path is None or not file_path.exists():
        raise HTTPException(status_code=404)

    if req.status == "completed":
        paper.download_count += 1
        db.commit()

    return FileResponse(
        str(file_path),
        media_type="application/pdf",
        filename=f"request-{req.id}.pdf",
    )
