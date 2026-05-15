"""Admin backstage. All routes require_admin. Five sections:
- index (dashboard quick-links)
- settings (system_settings runtime overrides + PDF desensitize toggle)
- gift (admin-initiated point adjustments)
- users (list + toggle is_active)
- requests (list + force-close with refund)
- reports (list + close-from-report)
"""
from __future__ import annotations

import logging
from typing import Optional

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import HelpRequest, PointTransaction, Report, SystemSetting, User
from ..points import REASON_ADMIN_GIFT, REASON_HELP_ACCEPTED, adjust_points
from ..runtime_config import as_bool, as_int, get_setting, set_setting
from ..security import require_admin
from ..services import force_close_request
from ..settings import settings as bootstrap
from ..templating import render
from ..urls import redirect


logger = logging.getLogger("lit-share.admin")
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ---------------------------------------------------------------------------
# Settings metadata — drives the /admin/settings form.
# `type` controls cast at save time; `default` is read from the bootstrap settings.
# ---------------------------------------------------------------------------

SETTING_KNOBS = [
    # --- 积分 / 时限 ---
    {"key": "SIGNIN_POINTS",            "type": "int",  "label": "每日签到积分",   "help": "用户每日签到一次获得的积分", "group": "积分 / 时限"},
    {"key": "REQUEST_TIMEOUT_DAYS",     "type": "int",  "label": "求助超时天数",   "help": "无人应助多少天后自动退分(scheduler 扫描)", "group": "积分 / 时限"},
    {"key": "CONFIRM_WINDOW_HOURS",     "type": "int",  "label": "自动确认窗口(小时)", "help": "应助上传后,求助者不操作多少小时自动确认", "group": "积分 / 时限"},
    {"key": "MAX_PDF_SIZE_MB",          "type": "int",  "label": "PDF 上传上限 (MB)", "group": "积分 / 时限"},
    {"key": "SAME_JOURNAL_MONTHLY_LIMIT","type": "int",  "label": "同期刊月度上限", "help": "单用户单期刊每月最多发布的求助数", "group": "积分 / 时限"},

    # --- 内容 / 安全 ---
    {"key": "REPORT_THRESHOLD",         "type": "int",  "label": "举报自动关闭阈值", "help": "单求助累计被举报多少次自动关闭", "group": "内容 / 安全"},
    {"key": "REPORTER_MIN_HELPS",       "type": "int",  "label": "举报人门槛",     "help": "应助被采纳累计多少次的用户才能举报", "group": "内容 / 安全"},
    {"key": "PDF_DESENSITIZE_ENABLED",  "type": "bool", "label": "PDF 脱敏下发",   "help": "ON: 下发脱敏版(去元数据+涂黑PII);OFF: 下发原版。仅影响下发,上传时永远生成脱敏版", "group": "内容 / 安全"},

    # --- 站点文案 ---
    {"key": "SITE_TITLE",               "type": "str",  "label": "站点名称",       "help": "导航/页面标题", "group": "站点文案"},
    {"key": "SITE_SLOGAN",              "type": "str",  "label": "站点 slogan",    "help": "首页大标题下的副标题", "group": "站点文案"},

    # --- 邮件 SMTP ---
    {"key": "SMTP_HOST",                "type": "str",  "label": "SMTP 服务器",   "help": "例: smtp.qq.com / smtp.gmail.com / smtp.163.com。留空则注册验证链接只打印到日志", "group": "邮件 SMTP"},
    {"key": "SMTP_PORT",                "type": "int",  "label": "SMTP 端口",     "help": "SSL 通常 465,STARTTLS 通常 587", "group": "邮件 SMTP"},
    {"key": "SMTP_USE_SSL",             "type": "bool", "label": "使用 SSL",      "help": "ON: SMTPS(端口 465);OFF: STARTTLS(端口 587)", "group": "邮件 SMTP"},
    {"key": "SMTP_USER",                "type": "str",  "label": "SMTP 用户名",   "help": "通常就是发件邮箱地址", "group": "邮件 SMTP"},
    {"key": "SMTP_PASS",                "type": "password", "label": "SMTP 密码 / 授权码", "help": "QQ/网易等需要在邮箱后台开启 SMTP 并使用「授权码」,不是登录密码", "group": "邮件 SMTP"},
    {"key": "SMTP_FROM",                "type": "str",  "label": "发件人地址",     "help": "出现在 From 头。不填则使用 SMTP_USER", "group": "邮件 SMTP"},
]


def _bootstrap_default(knob: dict):
    return getattr(bootstrap, knob["key"], "")


def _current_value(db: Session, knob: dict):
    cast = {"int": as_int, "bool": as_bool}.get(knob["type"], str)
    return get_setting(db, knob["key"], _bootstrap_default(knob), cast=cast)


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------

@router.get("")
def admin_index(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user_count = db.scalar(select(func.count(User.id))) or 0
    req_count = db.scalar(select(func.count(HelpRequest.id))) or 0
    open_count = db.scalar(select(func.count(HelpRequest.id)).where(HelpRequest.status == "open")) or 0
    report_count = db.scalar(select(func.count(Report.id))) or 0
    pdf_on = get_setting(db, "PDF_DESENSITIZE_ENABLED", bootstrap.PDF_DESENSITIZE_ENABLED, cast=as_bool)

    return render(
        request, "admin/index.html",
        current_user=user,
        nav="index",
        user_count=user_count, req_count=req_count,
        open_count=open_count, report_count=report_count,
        pdf_on=pdf_on,
    )


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

@router.get("/settings")
def settings_form(
    request: Request,
    saved: Optional[str] = None,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    items = []
    for knob in SETTING_KNOBS:
        items.append({
            **knob,
            "current": _current_value(db, knob),
            "default": _bootstrap_default(knob),
            "overridden": db.get(SystemSetting, knob["key"]) is not None,
        })
    return render(
        request, "admin/settings.html",
        current_user=user, nav="settings",
        items=items, saved=saved,
    )


@router.post("/settings")
async def settings_save(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    changed = 0
    for knob in SETTING_KNOBS:
        key = knob["key"]
        if knob["type"] == "bool":
            # Checkboxes only POST when checked; missing = False
            raw = "true" if key in form else "false"
        else:
            raw = (form.get(key) or "").strip()
            if not raw:
                continue
            # Validate per type before storing
            if knob["type"] == "int":
                try:
                    int(raw)
                except ValueError:
                    logger.warning("settings: bad int for %s: %r", key, raw)
                    continue

        existing = db.get(SystemSetting, key)
        if existing is None or existing.value != raw:
            set_setting(db, key, raw)
            changed += 1
            # Never log password values — they're stored only.
            shown = "***" if knob["type"] == "password" else repr(raw)
            logger.info("settings: %s -> %s (admin %s)", key, shown, user.email)

    db.commit()
    return redirect(request, f"/admin/settings?saved={changed}")


@router.post("/settings/reset")
def settings_reset(
    request: Request,
    key: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove a single override row, reverting to .env default."""
    row = db.get(SystemSetting, key)
    if row is not None:
        db.delete(row)
        db.commit()
        logger.info("settings: reset %s -> default (admin %s)", key, user.email)
    return redirect(request, "/admin/settings?saved=1")


# ---------------------------------------------------------------------------
# gift
# ---------------------------------------------------------------------------

@router.get("/gift")
def gift_form(
    request: Request,
    msg: Optional[str] = None,
    err: Optional[str] = None,
    user: User = Depends(require_admin),
):
    return render(
        request, "admin/gift.html",
        current_user=user, nav="gift",
        msg=msg, err=err,
    )


def _resolve_target(db: Session, target: str) -> Optional[User]:
    target = (target or "").strip()
    if not target:
        return None
    if target.isdigit():
        return db.get(User, int(target))
    # Try email
    try:
        norm = validate_email(target, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        return None
    return db.scalar(select(User).where(User.email == norm))


@router.post("/gift")
def gift_submit(
    request: Request,
    target: str = Form(...),
    delta: int = Form(...),
    note: str = Form(""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from urllib.parse import quote

    if delta == 0:
        return redirect(request, "/admin/gift?err=" + quote("积分变动不能为 0"))
    tgt = _resolve_target(db, target)
    if tgt is None:
        return redirect(request, "/admin/gift?err=" + quote(f"找不到用户「{target}」"))

    audit_note = f"by admin {user.email}: {note.strip()[:200]}"
    adjust_points(
        db, tgt.id, delta, REASON_ADMIN_GIFT,
        note=audit_note, allow_negative=True,
    )
    db.commit()
    msg = f"已给 {tgt.email} {'增加' if delta > 0 else '扣减'} {abs(delta)} 积分（现 {tgt.points}）"
    logger.info("gift: %s %+d (by %s)", tgt.email, delta, user.email)
    return redirect(request, "/admin/gift?msg=" + quote(msg))


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------

USER_PAGE_SIZE = 50


@router.get("/users")
def users_list(
    request: Request,
    page: int = Query(1, ge=1),
    q: str = "",
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    base_stmt = select(User)
    count_stmt = select(func.count(User.id))
    if q:
        like = f"%{q.lower()}%"
        base_stmt = base_stmt.where(
            (func.lower(User.email).like(like)) | (func.lower(User.nickname).like(like))
        )
        count_stmt = count_stmt.where(
            (func.lower(User.email).like(like)) | (func.lower(User.nickname).like(like))
        )
    total = db.scalar(count_stmt) or 0
    offset = (page - 1) * USER_PAGE_SIZE
    users = db.scalars(
        base_stmt.order_by(desc(User.created_at)).offset(offset).limit(USER_PAGE_SIZE)
    ).all()
    has_next = offset + len(users) < total
    return render(
        request, "admin/users.html",
        current_user=user, nav="users",
        users=users, total=total,
        page=page, has_next=has_next, q=q,
    )


@router.post("/users/{user_id}/toggle-active")
def user_toggle_active(
    request: Request,
    user_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if user_id == user.id:
        return redirect(request, "/admin/users")  # can't disable self silently
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    target.is_active = not target.is_active
    db.commit()
    logger.info("user %s is_active -> %s (by admin %s)", target.email, target.is_active, user.email)
    return redirect(request, "/admin/users")


# ---------------------------------------------------------------------------
# requests management
# ---------------------------------------------------------------------------

REQ_PAGE_SIZE = 50
STATUS_LABELS = {
    "open": "待应助", "claimed": "已认领", "awaiting_confirm": "待确认",
    "completed": "已完结", "closed": "已关闭", "expired": "已过期",
}


@router.get("/requests")
def requests_list(
    request: Request,
    page: int = Query(1, ge=1),
    status_filter: str = Query("", alias="status"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    base_stmt = select(HelpRequest, User.nickname, User.email).join(
        User, User.id == HelpRequest.requester_id
    )
    count_stmt = select(func.count(HelpRequest.id))
    if status_filter:
        base_stmt = base_stmt.where(HelpRequest.status == status_filter)
        count_stmt = count_stmt.where(HelpRequest.status == status_filter)
    total = db.scalar(count_stmt) or 0
    offset = (page - 1) * REQ_PAGE_SIZE
    rows = db.execute(
        base_stmt.order_by(desc(HelpRequest.created_at))
        .offset(offset).limit(REQ_PAGE_SIZE)
    ).all()
    items = [{"req": r, "nickname": n, "email": e} for (r, n, e) in rows]
    has_next = offset + len(items) < total

    return render(
        request, "admin/requests.html",
        current_user=user, nav="requests",
        items=items, total=total, status_labels=STATUS_LABELS,
        page=page, has_next=has_next, status_filter=status_filter,
    )


@router.post("/requests/{req_id}/close")
def request_force_close(
    request: Request,
    req_id: int,
    note: str = Form("admin 关闭"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    force_close_request(db, req, note=f"by admin {user.email}: {note.strip()[:200]}")
    db.commit()
    return redirect(request, f"/admin/requests?status={req.status}")


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------

@router.get("/reports")
def reports_list(
    request: Request,
    page: int = Query(1, ge=1),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count(Report.id))) or 0
    offset = (page - 1) * REQ_PAGE_SIZE
    rows = db.execute(
        select(Report, HelpRequest, User.email)
        .join(HelpRequest, HelpRequest.id == Report.request_id)
        .join(User, User.id == Report.reporter_id)
        .order_by(desc(Report.created_at))
        .offset(offset).limit(REQ_PAGE_SIZE)
    ).all()
    items = [{"r": rep, "req": req, "reporter_email": em} for (rep, req, em) in rows]
    has_next = offset + len(items) < total
    return render(
        request, "admin/reports.html",
        current_user=user, nav="reports",
        items=items, total=total, status_labels=STATUS_LABELS,
        page=page, has_next=has_next,
    )


@router.post("/reports/{rep_id}/dismiss")
def report_dismiss(
    request: Request,
    rep_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rep = db.get(Report, rep_id)
    if rep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    db.delete(rep)
    db.commit()
    logger.info("report %d dismissed by admin %s", rep_id, user.email)
    return redirect(request, "/admin/reports")
