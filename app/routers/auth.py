"""Auth flows: register (with email-verify stub), verify, login, logout.

Email verification is stubbed — the token URL is printed to the app log instead of
sent. When SMTP_HOST is configured later, swap _send_verify_email() for a real send.
"""
from __future__ import annotations

import logging
from typing import Optional

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import (
    SESSION_COOKIE,
    clear_session_cookie,
    current_user,
    hash_password,
    make_verify_token,
    read_verify_token,
    set_session_cookie,
    verify_password,
)
from ..settings import settings
from ..templating import render

logger = logging.getLogger("lit-share.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _normalize_email(raw: str) -> Optional[str]:
    try:
        info = validate_email(raw, check_deliverability=False)
        return info.normalized.lower()
    except EmailNotValidError:
        return None


def _send_verify_email(email: str, link: str) -> None:
    """Stub: log the verify link prominently so the dev / admin can copy it."""
    logger.warning("== EMAIL VERIFY STUB ==> to=%s link=%s", email, link)


def _abs_url(request: Request, path: str) -> str:
    """Compose a public-facing URL honoring root_path."""
    base = str(request.base_url).rstrip("/")
    return f"{base}{path}"


def _redirect(path: str, status_code: int = status.HTTP_303_SEE_OTHER) -> RedirectResponse:
    """Public-path redirect respecting reverse-proxy base path."""
    full = (settings.APP_BASE_PATH or "") + path
    return RedirectResponse(url=full or "/", status_code=status_code)


def _safe_next(raw: str) -> str:
    """Only allow same-origin internal paths under our base. Reject anything else."""
    if not raw or not raw.startswith("/"):
        return "/me"
    base = settings.APP_BASE_PATH or ""
    if base and raw.startswith(base + "/"):
        # Strip base because _redirect re-adds it.
        return raw[len(base):] or "/"
    if base and raw == base:
        return "/"
    return "/me"


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

@router.get("/register")
def register_form(request: Request, user: Optional[User] = Depends(current_user)):
    if user:
        return _redirect("/me")
    return render(request, "auth/register.html", current_user=user)


@router.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    nickname: str = Form(...),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    if user:
        return _redirect("/me")

    norm_email = _normalize_email(email)
    nickname = nickname.strip()
    error: Optional[str] = None
    if not norm_email:
        error = "请输入有效的邮箱地址"
    elif len(password) < 8:
        error = "密码至少 8 位"
    elif not (1 <= len(nickname) <= 64):
        error = "昵称长度需在 1–64 字符之间"

    if error:
        return render(
            request, "auth/register.html",
            current_user=None, error=error,
            form_email=email, form_nickname=nickname,
            status_code=400,
        )

    existing = db.scalar(select(User).where(User.email == norm_email))
    if existing is not None:
        return render(
            request, "auth/register.html",
            current_user=None, error="该邮箱已注册",
            form_email=email, form_nickname=nickname,
            status_code=400,
        )

    # First registration of ADMIN_EMAIL gets admin rights.
    is_admin = bool(settings.ADMIN_EMAIL) and norm_email == settings.ADMIN_EMAIL.lower()

    new_user = User(
        email=norm_email,
        password_hash=hash_password(password),
        nickname=nickname,
        points=0,
        is_admin=is_admin,
        is_active=True,
        email_verified=False,
    )
    db.add(new_user)
    db.commit()

    token = make_verify_token(norm_email)
    link = _abs_url(request, f"/auth/verify?token={token}")
    _send_verify_email(norm_email, link)

    return render(
        request, "auth/notice.html",
        current_user=None,
        title="注册成功，请验证邮箱",
        message=(
            f"我们已向 {norm_email} 发送验证邮件（当前为开发 stub，"
            f"验证链接已打印到服务器日志）。点击链接后即可登录。"
        ),
    )


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

@router.get("/verify")
def verify(request: Request, token: str = "", db: Session = Depends(get_db)):
    email = read_verify_token(token) if token else None
    if not email:
        return render(
            request, "auth/notice.html", current_user=None,
            title="验证链接无效或已过期", message="请返回登录页重新申请。",
            status_code=400,
        )
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user:
        return render(
            request, "auth/notice.html", current_user=None,
            title="账户不存在", message="请重新注册。",
            status_code=404,
        )
    if not user.email_verified:
        user.email_verified = True
        db.commit()
    return render(
        request, "auth/notice.html", current_user=None,
        title="邮箱已验证", message="现在可以登录使用了。",
        action_label="前往登录", action_url="/auth/login",
    )


# ---------------------------------------------------------------------------
# login / logout
# ---------------------------------------------------------------------------

@router.get("/login")
def login_form(request: Request, next: str = "", user: Optional[User] = Depends(current_user)):
    if user:
        return _redirect(_safe_next(next))
    return render(request, "auth/login.html", current_user=None, next_param=next)


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(""),
    db: Session = Depends(get_db),
):
    norm_email = _normalize_email(email)
    if not norm_email:
        return render(
            request, "auth/login.html", current_user=None,
            error="邮箱格式不正确", form_email=email,
            status_code=400,
        )
    user = db.scalar(select(User).where(User.email == norm_email))
    if not user or not verify_password(password, user.password_hash):
        return render(
            request, "auth/login.html", current_user=None,
            error="邮箱或密码错误", form_email=email,
            status_code=400,
        )
    if not user.is_active:
        return render(
            request, "auth/login.html", current_user=None,
            error="账户已被禁用，请联系管理员", form_email=email,
            status_code=403,
        )
    if not user.email_verified:
        # Regenerate the verify link so a stuck user can recover from the log.
        token = make_verify_token(user.email)
        link = _abs_url(request, f"/auth/verify?token={token}")
        _send_verify_email(user.email, link)
        return render(
            request, "auth/login.html", current_user=None,
            error="邮箱尚未验证，新的验证链接已发送（已打印到服务器日志）",
            form_email=email,
            status_code=403,
        )

    response = _redirect(_safe_next(next))
    set_session_cookie(response, user.id)
    return response


@router.post("/logout")
def logout(_user: User = Depends(current_user)):
    response = _redirect("/")
    clear_session_cookie(response)
    return response
