"""Auth primitives: password hashing, signed-cookie session, email-verify tokens, FastAPI deps."""
from __future__ import annotations

from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .settings import settings


SESSION_COOKIE = "litshare_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
VERIFY_TOKEN_MAX_AGE = 60 * 60 * 24  # 24 hours
BCRYPT_ROUNDS = 12

_session_signer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="litshare-session")
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


def set_session_cookie(response, user_id: int, request: Request) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        make_session_token(user_id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=not settings.DEBUG,
        path=cookie_path(request),
    )


def clear_session_cookie(response, request: Request) -> None:
    response.delete_cookie(SESSION_COOKIE, path=cookie_path(request))


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
