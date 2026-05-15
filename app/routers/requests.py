"""Help-request flows: publish (deduct bounty), lobby list, detail view.

M2 covers publishing + browsing. M3 adds the claim/upload/confirm machinery.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import HelpRequest, User
from ..points import REASON_PUBLISH_DEDUCT, InsufficientPoints, adjust_points
from ..runtime_config import as_int, get_setting
from ..security import current_user, require_login
from ..settings import settings
from ..templating import render
from ..timekit import CN_TZ, humanize_remaining, now_utc_naive
from ..urls import redirect

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

@router.get("/{req_id}")
def detail(
    request: Request,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    req, requester_nick = row

    helper_nick = None
    if req.claimed_by:
        helper_nick = db.scalar(select(User.nickname).where(User.id == req.claimed_by))

    return render(
        request, "requests/detail.html",
        current_user=viewer,
        req=req,
        requester_nickname=requester_nick,
        helper_nickname=helper_nick,
        remaining=humanize_remaining(req.request_deadline),
        is_owner=(viewer is not None and viewer.id == req.requester_id),
    )
