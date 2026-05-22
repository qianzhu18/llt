"""Auth primitives: password hashing, signed-cookie session, CSRF, email-verify tokens, FastAPI deps."""
from __future__ import annotations

import hmac
import secrets
from typing import Optional

import bcrypt
from fastapi import Depends, Form, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .settings import settings


SESSION_COOKIE = "litshare_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
CSRF_COOKIE = "litshare_csrf"
CSRF_MAX_AGE = 60 * 60 * 24 * 7  # 7 days
VERIFY_TOKEN_MAX_AGE = 60 * 60 * 24  # 24 hours
BCRYPT_ROUNDS = 12

_session_signer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="litshare-session")
_csrf_signer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="litshare-csrf")
_verify_signer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="litshare-email-verify")


def _to_bcrypt_bytes(plain: str) -> bytes:
    # bcrypt silently truncates beyond 72 bytes; do it explicitly for predictability.
    return plain.encode("utf-8")[:72]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_to_bcrypt_bytes(plain), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(plain), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def make_session_token(user_id: int) -> str:
    return _session_signer.dumps(user_id)


def read_session_token(token: str) -> Optional[int]:
    try:
        uid = _session_signer.loads(token, max_age=SESSION_MAX_AGE)
        return int(uid)
    except (BadSignature, SignatureExpired, ValueError):
        return None


def make_verify_token(email: str) -> str:
    return _verify_signer.dumps(email)


def read_verify_token(token: str) -> Optional[str]:
    try:
        email = _verify_signer.loads(token, max_age=VERIFY_TOKEN_MAX_AGE)
        return str(email)
    except (BadSignature, SignatureExpired, ValueError):
        return None


def cookie_path(request: Request) -> str:
    """Cookie path must match the public base; otherwise browsers won't replay it.
    Derived from X-Forwarded-Prefix on this request (see app.main middleware)."""
    return request.scope.get("root_path", "") or "/"


def cookie_secure(request: Request) -> bool:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").lower()
    return proto == "https"


def set_session_cookie(response, user_id: int, request: Request) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        make_session_token(user_id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(request),
        path=cookie_path(request),
    )


def clear_session_cookie(response, request: Request) -> None:
    response.delete_cookie(SESSION_COOKIE, path=cookie_path(request))


def make_csrf_token() -> str:
    return _csrf_signer.dumps(secrets.token_urlsafe(32))


def read_csrf_token(token: str) -> Optional[str]:
    try:
        value = _csrf_signer.loads(token, max_age=CSRF_MAX_AGE)
        return str(value)
    except (BadSignature, SignatureExpired, ValueError):
        return None


def set_csrf_cookie(response, request: Request, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=CSRF_MAX_AGE,
        httponly=False,  # SPA needs to read this via JS
        samesite="lax",
        secure=cookie_secure(request),
        path=cookie_path(request),
    )


def ensure_csrf_token(request: Request) -> str:
    token = request.cookies.get(CSRF_COOKIE) or ""
    if read_csrf_token(token) is None:
        token = make_csrf_token()
    return token


def csrf_valid(request: Request, form_token: str) -> bool:
    cookie_token = request.cookies.get(CSRF_COOKIE) or ""
    if not form_token or not cookie_token:
        return False
    if not hmac.compare_digest(cookie_token, form_token):
        return False
    return read_csrf_token(cookie_token) is not None


def require_csrf(request: Request, csrf_token: str = Form("", alias="_csrf")) -> None:
    if not csrf_valid(request, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf_invalid")


def require_csrf_header(request: Request) -> None:
    """CSRF check for JSON API: reads token from X-CSRF-Token header."""
    header_token = request.headers.get("x-csrf-token", "")
    if not csrf_valid(request, header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf_invalid")


def current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    uid = read_session_token(token)
    if uid is None:
        return None
    user = db.get(User, uid)
    if user is None or not user.is_active:
        return None
    return user


def require_login(user: Optional[User] = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login_required")
    return user


def require_admin(user: User = Depends(require_login)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_required")
    return user
