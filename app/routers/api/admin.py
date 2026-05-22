"""JSON API admin endpoints for the Vue SPA."""
from __future__ import annotations

import logging
from typing import Optional

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...email_send import send_email, smtp_status
from ...models import HelpRequest, PointTransaction, Report, SystemSetting, User
from ...points import REASON_ADMIN_GIFT, REASON_HELP_ACCEPTED, adjust_points
from ...runtime_config import as_bool, as_int, get_setting, set_setting
from ...security import require_admin, require_csrf_header
from ...services import force_close_request
from ...settings import settings as bootstrap

logger = logging.getLogger("lit-share.api.admin")
router = APIRouter(prefix="/api/v1/admin", tags=["api-admin"], dependencies=[Depends(require_admin)])

SETTING_KNOBS = [
    {"key": "SIGNIN_POINTS", "type": "int", "label": "每日签到积分", "help": "用户每日签到一次获得的积分", "group": "积分 / 时限"},
    {"key": "REQUEST_TIMEOUT_DAYS", "type": "int", "label": "求助超时天数", "help": "无人应助多少天后自动退分", "group": "积分 / 时限"},
    {"key": "CONFIRM_WINDOW_HOURS", "type": "int", "label": "自动确认窗口(小时)", "help": "应助上传后多少小时自动确认", "group": "积分 / 时限"},
    {"key": "MAX_PDF_SIZE_MB", "type": "int", "label": "PDF 上传上限 (MB)", "group": "积分 / 时限"},
    {"key": "SAME_JOURNAL_MONTHLY_LIMIT", "type": "int", "label": "同期刊月度上限", "group": "积分 / 时限"},
    {"key": "REPORT_THRESHOLD", "type": "int", "label": "举报自动关闭阈值", "group": "内容 / 安全"},
    {"key": "REPORTER_MIN_HELPS", "type": "int", "label": "举报人门槛", "group": "内容 / 安全"},
    {"key": "PDF_DESENSITIZE_ENABLED", "type": "bool", "label": "PDF 脱敏下发", "group": "内容 / 安全"},
    {"key": "SITE_TITLE", "type": "str", "label": "站点名称", "group": "站点文案"},
    {"key": "SITE_SLOGAN", "type": "str", "label": "站点 slogan", "group": "站点文案"},
    {"key": "SMTP_HOST", "type": "str", "label": "SMTP 服务器", "group": "邮件 SMTP"},
    {"key": "SMTP_PORT", "type": "int", "label": "SMTP 端口", "group": "邮件 SMTP"},
    {"key": "SMTP_USE_SSL", "type": "bool", "label": "使用 SSL", "group": "邮件 SMTP"},
    {"key": "SMTP_USER", "type": "str", "label": "SMTP 用户名", "group": "邮件 SMTP"},
    {"key": "SMTP_PASS", "type": "password", "label": "SMTP 密码 / 授权码", "group": "邮件 SMTP"},
    {"key": "SMTP_FROM", "type": "str", "label": "发件人地址", "group": "邮件 SMTP"},
]


def _bootstrap_default(knob: dict):
    return getattr(bootstrap, knob["key"], "")


def _current_value(db: Session, knob: dict):
    cast_map = {"int": as_int, "bool": as_bool}
    return get_setting(db, knob["key"], _bootstrap_default(knob), cast=cast_map.get(knob["type"], str))


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

@router.get("")
def admin_overview(db: Session = Depends(get_db)):
    return {
        "users": db.scalar(select(func.count(User.id))) or 0,
        "total_requests": db.scalar(select(func.count(HelpRequest.id))) or 0,
        "open_requests": db.scalar(select(func.count(HelpRequest.id)).where(HelpRequest.status == "open")) or 0,
        "reports": db.scalar(select(func.count(Report.id))) or 0,
        "pdf_desensitize": get_setting(db, "PDF_DESENSITIZE_ENABLED", bootstrap.PDF_DESENSITIZE_ENABLED, cast=as_bool),
    }


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    items = []
    for knob in SETTING_KNOBS:
        items.append({
            **knob,
            "current": _current_value(db, knob),
            "default": str(_bootstrap_default(knob)),
            "overridden": db.get(SystemSetting, knob["key"]) is not None,
        })
    return {"items": items, "smtp": smtp_status(db)}


class SaveSettingsBody(BaseModel):
    values: dict[str, str]
    toggles: list[str] = []  # keys that should be "true" (checkboxes)


@router.post("/settings")
def save_settings(
    body: SaveSettingsBody,
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    changed = 0
    for knob in SETTING_KNOBS:
        key = knob["key"]
        if knob["type"] == "bool":
            raw = "true" if key in body.toggles else "false"
        else:
            raw = (body.values.get(key) or "").strip()
            if not raw:
                continue
            if knob["type"] == "int":
                try:
                    int(raw)
                except ValueError:
                    continue
        existing = db.get(SystemSetting, key)
        if existing is None or existing.value != raw:
            set_setting(db, key, raw)
            changed += 1
    db.commit()
    return {"ok": True, "changed": changed}


class ResetSettingBody(BaseModel):
    key: str


@router.post("/settings/reset")
def reset_setting(
    body: ResetSettingBody,
    _csrf: None = Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    row = db.get(SystemSetting, body.key)
    if row is not None:
        db.delete(row)
        db.commit()
    return {"ok": True}


class TestEmailBody(BaseModel):
    email: str


@router.post("/settings/test-email")
def test_email(
    body: TestEmailBody,
    _csrf: None = Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    try:
        normalized = validate_email(body.email, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        return JSONResponse({"detail": "邮箱格式不正确"}, status_code=400)

    status_info = smtp_status(db)
    if not status_info["configured"]:
        return JSONResponse({"detail": "SMTP_HOST 未配置"}, status_code=400)

    site_title = get_setting(db, "SITE_TITLE", bootstrap.SITE_TITLE)
    result = send_email(
        db, to=normalized,
        subject=f"[{site_title}] SMTP 测试邮件",
        body=f"这是一封来自「{site_title}」的 SMTP 测试邮件。\n\n发件服务器：{status_info['host']}:{status_info['port']}",
    )
    if result["mode"] == "smtp":
        return {"ok": True, "message": f"测试邮件已发送到 {normalized}"}
    return JSONResponse({"detail": f"发送失败：{result['detail']}"}, status_code=500)


# ---------------------------------------------------------------------------
# Gift points
# ---------------------------------------------------------------------------

class GiftBody(BaseModel):
    target: str
    delta: int
    note: str = ""


def _resolve_target(db: Session, target: str) -> Optional[User]:
    target = target.strip()
    if not target:
        return None
    if target.isdigit():
        return db.get(User, int(target))
    try:
        norm = validate_email(target, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        return None
    return db.scalar(select(User).where(User.email == norm))


@router.post("/gift")
def gift_points(
    body: GiftBody,
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if body.delta == 0:
        return JSONResponse({"detail": "积分变动不能为 0"}, status_code=400)
    tgt = _resolve_target(db, body.target)
    if tgt is None:
        return JSONResponse({"detail": f"找不到用户「{body.target}」"}, status_code=400)

    audit_note = f"by admin {user.email}: {body.note.strip()[:200]}"
    adjust_points(db, tgt.id, body.delta, REASON_ADMIN_GIFT, note=audit_note, allow_negative=True)
    db.commit()
    msg = f"已给 {tgt.email} {'增加' if body.delta > 0 else '扣减'} {abs(body.delta)} 积分（现 {tgt.points}）"
    return {"ok": True, "message": msg}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

USER_PAGE_SIZE = 50


@router.get("/users")
def list_users(
    page: int = Query(1, ge=1),
    q: str = "",
    db: Session = Depends(get_db),
):
    base_stmt = select(User)
    count_stmt = select(func.count(User.id))
    if q:
        like = f"%{q.lower()}%"
        cond = (func.lower(User.email).like(like)) | (func.lower(User.nickname).like(like))
        base_stmt = base_stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = db.scalar(count_stmt) or 0
    offset = (page - 1) * USER_PAGE_SIZE
    users = db.scalars(
        base_stmt.order_by(desc(User.created_at)).offset(offset).limit(USER_PAGE_SIZE)
    ).all()

    return {
        "items": [
            {
                "id": u.id, "email": u.email, "nickname": u.nickname,
                "points": u.points, "is_admin": u.is_admin, "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "total_pages": max(1, (total + USER_PAGE_SIZE - 1) // USER_PAGE_SIZE),
    }


@router.post("/users/{user_id}/toggle-active")
def toggle_user(
    user_id: int,
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if user_id == user.id:
        return JSONResponse({"detail": "不能禁用自己"}, status_code=400)
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404)
    target.is_active = not target.is_active
    db.commit()
    return {"ok": True, "is_active": target.is_active}


# ---------------------------------------------------------------------------
# Requests management
# ---------------------------------------------------------------------------

REQ_PAGE_SIZE = 50


@router.get("/requests")
def list_requests(
    page: int = Query(1, ge=1),
    status_filter: str = Query("", alias="status"),
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
        base_stmt.order_by(desc(HelpRequest.created_at)).offset(offset).limit(REQ_PAGE_SIZE)
    ).all()

    return {
        "items": [
            {
                "id": r.id, "title": r.title, "status": r.status, "bounty": r.bounty,
                "requester_nickname": n, "requester_email": e,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r, n, e in rows
        ],
        "total": total,
        "page": page,
        "total_pages": max(1, (total + REQ_PAGE_SIZE - 1) // REQ_PAGE_SIZE),
    }


class CloseRequestBody(BaseModel):
    note: str = "admin 关闭"


@router.post("/requests/{req_id}/close")
def close_request(
    req_id: int,
    body: CloseRequestBody,
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    req = db.get(HelpRequest, req_id)
    if req is None:
        raise HTTPException(status_code=404)
    force_close_request(db, req, note=f"by admin {user.email}: {body.note.strip()[:200]}")
    db.commit()
    return {"ok": True, "status": req.status}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@router.get("/reports")
def list_reports(
    page: int = Query(1, ge=1),
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

    return {
        "items": [
            {
                "id": rep.id, "reason": rep.reason,
                "request_id": req.id, "request_title": req.title, "request_status": req.status,
                "reporter_email": em,
                "created_at": rep.created_at.isoformat() if rep.created_at else None,
            }
            for rep, req, em in rows
        ],
        "total": total,
        "page": page,
        "total_pages": max(1, (total + REQ_PAGE_SIZE - 1) // REQ_PAGE_SIZE),
    }


@router.post("/reports/{rep_id}/dismiss")
def dismiss_report(
    rep_id: int,
    _csrf: None = Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    rep = db.get(Report, rep_id)
    if rep is None:
        raise HTTPException(status_code=404)
    db.delete(rep)
    db.commit()
    return {"ok": True}
