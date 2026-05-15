"""Help-request flows: publish, lobby, detail, claim/release/upload/confirm/reject, download."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Attachment, HelpRequest, LibraryPaper, PointTransaction, Report, User
from ..pdf_redact import safe_desensitize
from ..points import REASON_HELP_ACCEPTED, REASON_PUBLISH_DEDUCT, InsufficientPoints, adjust_points
from ..runtime_config import as_bool, as_int, get_setting
from ..security import current_user, require_login
from ..services import (
    UPLOADS_DIR,
    complete_request,
    force_close_request,
    latest_attachment,
    library_files,
    reject_upload,
)
from ..settings import settings
from ..templating import render
from ..timekit import CN_TZ, humanize_remaining, now_utc_naive
from ..urls import redirect


logger = logging.getLogger("lit-share.requests")

router = APIRouter(prefix="/requests", tags=["requests"])


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
    """Count this user's posts on the same journal since the CN-month start."""
    if not journal_norm:
        return 0
    return db.scalar(
        select(func.count(HelpRequest.id)).where(
            HelpRequest.requester_id == user_id,
            func.lower(HelpRequest.journal) == journal_norm,
            HelpRequest.created_at >= _cn_month_start_utc(),
        )
    ) or 0


# ---------------------------------------------------------------------------
# lobby
# ---------------------------------------------------------------------------

@router.get("")
def lobby(
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(current_user),
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
            "req": req,
            "requester_nickname": nick,
            "remaining": humanize_remaining(req.request_deadline),
        }
        for req, nick in rows
    ]
    has_next = offset + len(items) < total

    return render(
        request, "requests/lobby.html",
        current_user=viewer, items=items,
        page=page, has_next=has_next, total=total,
    )


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------

@router.get("/new")
def new_form(
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    timeout_days = get_setting(db, "REQUEST_TIMEOUT_DAYS", settings.REQUEST_TIMEOUT_DAYS, cast=as_int)
    return render(
        request, "requests/new.html",
        current_user=user,
        bounty_options=BOUNTY_OPTIONS,
        timeout_days=timeout_days,
        current_year=CURRENT_YEAR,
        form={},
    )


@router.post("/new")
def new_submit(
    request: Request,
    title: str = Form(...),
    authors: str = Form(...),
    journal: str = Form(""),
    year: int = Form(...),
    extra: str = Form(""),
    bounty: int = Form(...),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    title = title.strip()
    authors = authors.strip()
    journal = journal.strip()
    extra = extra.strip()

    timeout_days = get_setting(db, "REQUEST_TIMEOUT_DAYS", settings.REQUEST_TIMEOUT_DAYS, cast=as_int)
    journal_limit = get_setting(db, "SAME_JOURNAL_MONTHLY_LIMIT", settings.SAME_JOURNAL_MONTHLY_LIMIT, cast=as_int)

    def _err(msg: str, code: int = 400):
        return render(
            request, "requests/new.html",
            current_user=user, error=msg,
            bounty_options=BOUNTY_OPTIONS, timeout_days=timeout_days,
            current_year=CURRENT_YEAR,
            form={"title": title, "authors": authors, "journal": journal,
                  "year": year, "extra": extra, "bounty": bounty},
            status_code=code,
        )

    if not title:
        return _err("标题不能为空")
    if len(title) > 500:
        return _err("标题过长（≤500 字）")
    if not authors:
        return _err("作者不能为空")
    if len(authors) > 500:
        return _err("作者过长（≤500 字）")
    if len(journal) > 300:
        return _err("期刊名过长（≤300 字）")
    if not (MIN_YEAR <= year <= MAX_YEAR):
        return _err(f"年份需在 {MIN_YEAR}–{MAX_YEAR} 之间")
    if bounty not in BOUNTY_OPTIONS:
        return _err("悬赏积分必须是 10/20/30/50 之一")

    journal_norm = _normalize_journal(journal)
    if journal_norm:
        used = _journal_quota_used_this_month(db, user.id, journal_norm)
        if used >= journal_limit:
            return _err(
                f"本月在「{journal}」上已发布 {used} 篇，已达单期刊月度上限 {journal_limit} 篇。"
                f"请明月再试，或换一篇其他期刊的求助。"
            )

    deadline = now_utc_naive() + timedelta(days=timeout_days)

    new_req = HelpRequest(
        requester_id=user.id,
        title=title, authors=authors, journal=journal, year=year, extra=extra,
        bounty=bounty, status="open",
        request_deadline=deadline,
    )
    db.add(new_req)
    db.flush()  # populate new_req.id for ref_request_id

    try:
        adjust_points(
            db, user.id, -bounty, REASON_PUBLISH_DEDUCT,
            ref_request_id=new_req.id, note=f"bounty for #{new_req.id}",
        )
    except InsufficientPoints:
        db.rollback()
        return _err(f"积分不足（需 {bounty},当前 {user.points}）。可先签到攒积分。")

    db.commit()
    return redirect(request, f"/requests/{new_req.id}")


# ---------------------------------------------------------------------------
# detail
# ---------------------------------------------------------------------------

def _flash_redirect(request: Request, req_id: int, err: str):
    from urllib.parse import quote
    return redirect(request, f"/requests/{req_id}?err={quote(err)}")


def _flash_ok(request: Request, req_id: int, msg: str):
    from urllib.parse import quote
    return redirect(request, f"/requests/{req_id}?msg={quote(msg)}")


@router.get("/{req_id}")
def detail(
    request: Request,
    req_id: int,
    err: str = "",
    msg: str = "",
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(current_user),
):
    row = db.execute(
        select(HelpRequest, User.nickname)
        .join(User, User.id == HelpRequest.requester_id)
        .where(HelpRequest.id == req_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    req, requester_nick = row

    helper_nick = None
    if req.claimed_by:
        helper_nick = db.scalar(select(User.nickname).where(User.id == req.claimed_by))

    is_owner = viewer is not None and viewer.id == req.requester_id
    is_helper = viewer is not None and viewer.id == req.claimed_by

    if req.status == "open":
        remaining = humanize_remaining(req.request_deadline)
    elif req.status == "awaiting_confirm":
        remaining = humanize_remaining(req.confirm_deadline)
    else:
        remaining = None

    max_mb = get_setting(db, "MAX_PDF_SIZE_MB", settings.MAX_PDF_SIZE_MB, cast=as_int)
    desensitize_on = get_setting(
        db, "PDF_DESENSITIZE_ENABLED", settings.PDF_DESENSITIZE_ENABLED, cast=as_bool,
    )

    # Report-button visibility: viewer is not anonymous, not owner/helper,
    # and has accumulated REPORTER_MIN_HELPS accepted helps.
    can_report = False
    already_reported = False
    if viewer is not None and viewer.id != req.requester_id and viewer.id != (req.claimed_by or 0):
        min_helps = get_setting(
            db, "REPORTER_MIN_HELPS", settings.REPORTER_MIN_HELPS, cast=as_int,
        )
        helps_count = db.scalar(
            select(func.count(PointTransaction.id)).where(
                PointTransaction.user_id == viewer.id,
                PointTransaction.reason == REASON_HELP_ACCEPTED,
            )
        ) or 0
        can_report = helps_count >= min_helps
        if can_report:
            already_reported = db.scalar(
                select(func.count(Report.id)).where(
                    Report.request_id == req.id,
                    Report.reporter_id == viewer.id,
                )
            ) > 0

    return render(
        request, "requests/detail.html",
        current_user=viewer,
        req=req,
        requester_nickname=requester_nick,
        helper_nickname=helper_nick,
        remaining=remaining,
        is_owner=is_owner,
        is_helper=is_helper,
        max_mb=max_mb,
        desensitize_on=desensitize_on,
        can_report=can_report,
        already_reported=already_reported,
        flash_err=err,
        flash_msg=msg,
    )


# ---------------------------------------------------------------------------
# state transitions
# ---------------------------------------------------------------------------

@router.post("/{req_id}/claim")
def claim(
    request: Request,
    req_id: int,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if req.status != "open":
        return _flash_redirect(request, req_id, "当前状态不可认领")
    if req.requester_id == user.id:
        return _flash_redirect(request, req_id, "不能应助自己发布的求助")
    req.status = "claimed"
    req.claimed_by = user.id
    req.claimed_at = now_utc_naive()
    db.commit()
    return redirect(request, f"/requests/{req_id}")


@router.post("/{req_id}/release")
def release(
    request: Request,
    req_id: int,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if req.status != "claimed":
        return _flash_redirect(request, req_id, "已上传或已完结的求助不能放弃")
    if req.claimed_by != user.id:
        return _flash_redirect(request, req_id, "只有应助者可以放弃")
    req.status = "open"
    req.claimed_by = None
    req.claimed_at = None
    db.commit()
    return redirect(request, f"/requests/{req_id}")


@router.post("/{req_id}/upload")
async def upload(
    request: Request,
    req_id: int,
    pdf: UploadFile = File(...),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if req.status != "claimed":
        return _flash_redirect(request, req_id, "当前状态不允许上传")
    if req.claimed_by != user.id:
        return _flash_redirect(request, req_id, "只有当前应助者可以上传")

    max_mb = get_setting(db, "MAX_PDF_SIZE_MB", settings.MAX_PDF_SIZE_MB, cast=as_int)
    max_bytes = max_mb * 1024 * 1024

    contents = await pdf.read()
    if len(contents) == 0:
        return _flash_redirect(request, req_id, "请选择一个 PDF 文件")
    if len(contents) > max_bytes:
        return _flash_redirect(request, req_id, f"PDF 不能超过 {max_mb}MB（当前 {len(contents)//1048576}MB）")
    if len(contents) < 1024:
        return _flash_redirect(request, req_id, "PDF 文件太小，看起来不像有效内容")
    if contents[:5] != b"%PDF-":
        return _flash_redirect(request, req_id, "不是有效的 PDF（魔数校验失败）")

    ts = int(time.time())
    raw_path = UPLOADS_DIR / f"req{req.id}_h{user.id}_{ts}.pdf"
    raw_path.write_bytes(contents)

    # Sanitize at upload time regardless of admin toggle — the toggle controls SERVING,
    # not storage. This way flipping the toggle has zero-latency effect on downloads.
    sani_path = UPLOADS_DIR / f"req{req.id}_h{user.id}_{ts}.sanitized.pdf"
    stats = safe_desensitize(str(raw_path), str(sani_path))
    desensitized = bool(stats and sani_path.exists())
    if stats:
        logger.info("upload req #%d: sanitize stats=%s", req.id, stats)
    else:
        logger.warning("upload req #%d: sanitize FAILED — only original retained", req.id)

    db.add(Attachment(
        request_id=req.id,
        helper_id=user.id,
        original_path=str(raw_path),
        sanitized_path=str(sani_path) if desensitized else "",
        desensitized=desensitized,
        size_bytes=len(contents),
    ))

    confirm_hours = get_setting(
        db, "CONFIRM_WINDOW_HOURS", settings.CONFIRM_WINDOW_HOURS, cast=as_int,
    )
    now = now_utc_naive()
    req.status = "awaiting_confirm"
    req.uploaded_at = now
    req.confirm_deadline = now + timedelta(hours=confirm_hours)
    db.commit()

    return redirect(request, f"/requests/{req.id}")


@router.post("/{req_id}/confirm")
def confirm(
    request: Request,
    req_id: int,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if req.requester_id != user.id:
        return _flash_redirect(request, req_id, "只有求助者可以确认")
    if req.status != "awaiting_confirm":
        return _flash_redirect(request, req_id, "当前状态不可确认")
    try:
        complete_request(db, req)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.exception("confirm failed for req %d", req_id)
        return _flash_redirect(request, req_id, f"确认失败: {e}")
    return redirect(request, f"/requests/{req_id}")


@router.post("/{req_id}/reject")
def reject(
    request: Request,
    req_id: int,
    reason: str = Form(""),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if req.requester_id != user.id:
        return _flash_redirect(request, req_id, "只有求助者可以驳回")
    if req.status != "awaiting_confirm":
        return _flash_redirect(request, req_id, "当前状态不可驳回")
    reject_upload(db, req, reason.strip()[:500])
    db.commit()
    return redirect(request, f"/requests/{req_id}")


@router.post("/{req_id}/report")
def report(
    request: Request,
    req_id: int,
    reason: str = Form(...),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if req.requester_id == user.id:
        return _flash_redirect(request, req_id, "不能举报自己发布的求助")
    reason = reason.strip()
    if not reason:
        return _flash_redirect(request, req_id, "请填写举报原因")

    min_helps = get_setting(db, "REPORTER_MIN_HELPS", settings.REPORTER_MIN_HELPS, cast=as_int)
    helps_count = db.scalar(
        select(func.count(PointTransaction.id)).where(
            PointTransaction.user_id == user.id,
            PointTransaction.reason == REASON_HELP_ACCEPTED,
        )
    ) or 0
    if helps_count < min_helps:
        return _flash_redirect(request, req_id, f"举报门槛：需累计被采纳应助 ≥ {min_helps} 次（你目前 {helps_count}）")

    already = db.scalar(
        select(func.count(Report.id)).where(
            Report.request_id == req.id, Report.reporter_id == user.id,
        )
    ) or 0
    if already:
        return _flash_redirect(request, req_id, "你已举报过这条求助")

    db.add(Report(request_id=req.id, reporter_id=user.id, reason=reason[:255]))
    db.flush()

    threshold = get_setting(db, "REPORT_THRESHOLD", settings.REPORT_THRESHOLD, cast=as_int)
    distinct_reporters = db.scalar(
        select(func.count(func.distinct(Report.reporter_id))).where(Report.request_id == req.id)
    ) or 0

    auto_closed = False
    if distinct_reporters >= threshold and req.status not in ("closed", "expired", "completed"):
        force_close_request(
            db, req, note=f"自动关闭：举报达 {distinct_reporters}/{threshold} 次",
        )
        auto_closed = True

    db.commit()
    logger.info("report req #%d by user %d (count=%d, auto_close=%s)",
                req.id, user.id, distinct_reporters, auto_closed)
    return _flash_ok(request, req_id, "举报已提交" + ("，求助已自动关闭" if auto_closed else ""))


@router.get("/{req_id}/download")
def download(
    req_id: int,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    want_sani = get_setting(
        db, "PDF_DESENSITIZE_ENABLED", settings.PDF_DESENSITIZE_ENABLED, cast=as_bool,
    )

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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        if want_sani and att.sanitized_path and Path(att.sanitized_path).exists():
            file_path = Path(att.sanitized_path)
        else:
            file_path = Path(att.original_path)
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    if file_path is None or not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return FileResponse(
        str(file_path),
        media_type="application/pdf",
        filename=f"request-{req.id}.pdf",
    )
