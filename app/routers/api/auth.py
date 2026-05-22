"""JSON API auth endpoints for the Vue SPA."""
from __future__ import annotations

import logging
from typing import Optional

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...email_send import send_verify_email
from ...models import User
from ...runtime_config import get_setting
from ...security import (
    clear_session_cookie,
    current_user,
    hash_password,
    make_verify_token,
    read_verify_token,
    require_csrf_header,
    set_session_cookie,
    verify_password,
)
from ...settings import settings

logger = logging.getLogger("lit-share.api.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["api-auth"])


class RegisterBody(BaseModel):
    email: EmailStr
    nickname: str
    password: str


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class ResendVerifyBody(BaseModel):
    email: EmailStr


def _normalize_email(raw: str) -> Optional[str]:
    try:
        info = validate_email(raw, check_deliverability=False)
        return info.normalized.lower()
    except EmailNotValidError:
        return None


def _abs_url(request: Request, path: str) -> str:
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    from ...urls import public_url
    return f"{scheme}://{host}{public_url(request, path)}"


def _user_json(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "nickname": user.nickname,
        "points": user.points,
        "is_admin": user.is_admin,
        "email_verified": user.email_verified,
    }


@router.get("/me")
def me(user: Optional[User] = Depends(current_user)):
    if not user:
        return JSONResponse({"detail": "login_required"}, status_code=401)
    return _user_json(user)


@router.post("/register")
def register(
    body: RegisterBody,
    request: Request,
    _csrf: None = Depends(require_csrf_header),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    if user:
        return JSONResponse({"detail": "已登录", "user": _user_json(user)}, status_code=400)

    norm_email = _normalize_email(body.email)
    nickname = body.nickname.strip()

    if not norm_email:
        return JSONResponse({"detail": "请输入有效的邮箱地址"}, status_code=400)
    if len(body.password) < 8:
        return JSONResponse({"detail": "密码至少 8 位"}, status_code=400)
    if not (1 <= len(nickname) <= 64):
        return JSONResponse({"detail": "昵称长度需在 1–64 字符之间"}, status_code=400)

    existing = db.scalar(select(User).where(User.email == norm_email))
    if existing is not None:
        return JSONResponse({"detail": "该邮箱已注册"}, status_code=400)

    is_admin = bool(settings.ADMIN_EMAIL) and norm_email == settings.ADMIN_EMAIL.lower()

    new_user = User(
        email=norm_email,
        password_hash=hash_password(body.password),
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
    site_title = get_setting(db, "SITE_TITLE", settings.SITE_TITLE)
    result = send_verify_email(db, norm_email, link, site_title)

    if result["mode"] == "smtp":
        message = f"已向 {norm_email} 发送验证邮件，请查收。"
    elif result["mode"] == "log":
        message = "系统暂未配置 SMTP，验证链接已打印到服务器日志。请联系管理员。"
    else:
        message = f"邮件发送遇到问题：{result['detail']}。请联系管理员。"

    return {"message": message, "user": _user_json(new_user)}


@router.post("/login")
def login(
    body: LoginBody,
    request: Request,
    _csrf: None = Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    norm_email = _normalize_email(body.email)
    if not norm_email:
        return JSONResponse({"detail": "邮箱格式不正确"}, status_code=400)

    user = db.scalar(select(User).where(User.email == norm_email))
    if not user or not verify_password(body.password, user.password_hash):
        return JSONResponse({"detail": "邮箱或密码错误"}, status_code=400)
    if not user.is_active:
        return JSONResponse({"detail": "账户已被禁用，请联系管理员"}, status_code=403)
    if not user.email_verified:
        token = make_verify_token(user.email)
        link = _abs_url(request, f"/auth/verify?token={token}")
        site_title = get_setting(db, "SITE_TITLE", settings.SITE_TITLE)
        result = send_verify_email(db, user.email, link, site_title)
        if result["mode"] == "smtp":
            err = "邮箱尚未验证，新的验证链接已发送到邮箱"
        else:
            err = "邮箱尚未验证，验证链接已打印到服务器日志"
        return JSONResponse({"detail": err}, status_code=403)

    response = JSONResponse({"user": _user_json(user)})
    set_session_cookie(response, user.id, request)
    return response


@router.post("/logout")
def logout(
    request: Request,
    _csrf: None = Depends(require_csrf_header),
):
    response = JSONResponse({"ok": True})
    clear_session_cookie(response, request)
    return response


@router.post("/resend-verify")
def resend_verify(
    body: ResendVerifyBody,
    request: Request,
    _csrf: None = Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    norm_email = _normalize_email(body.email)
    message = "如果这个邮箱尚未完成验证，我们已经重新发送了一封验证邮件。"

    if norm_email:
        user = db.scalar(select(User).where(User.email == norm_email))
        if user and user.email_verified:
            return JSONResponse({"detail": "这个邮箱已经验证过，直接登录即可"}, status_code=400)
        elif user:
            token = make_verify_token(user.email)
            link = _abs_url(request, f"/auth/verify?token={token}")
            site_title = get_setting(db, "SITE_TITLE", settings.SITE_TITLE)
            result = send_verify_email(db, user.email, link, site_title)
            if result["mode"] == "log":
                message = "验证链接已重新生成；如果站点还没配置 SMTP，请联系管理员。"
            elif result["mode"] == "error":
                message = "邮件发送遇到问题，验证链接已回退到服务器日志。"

    return {"message": message}
