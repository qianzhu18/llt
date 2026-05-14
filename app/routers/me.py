"""Personal center shell — requires login. M1 only shows account info + edit nickname.
Request lists / activity will be filled in M2/M3."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import require_login
from ..settings import settings
from ..templating import render

router = APIRouter(tags=["me"])


def _redirect(path: str) -> RedirectResponse:
    full = (settings.APP_BASE_PATH or "") + path
    return RedirectResponse(url=full or "/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/me")
def me_index(request: Request, user: User = Depends(require_login)):
    return render(request, "me/index.html", current_user=user)


@router.get("/me/profile")
def profile_form(request: Request, user: User = Depends(require_login)):
    return render(request, "me/profile.html", current_user=user)


@router.post("/me/profile")
def profile_submit(
    request: Request,
    nickname: str = Form(...),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    nickname = nickname.strip()
    if not (1 <= len(nickname) <= 64):
        return render(
            request, "me/profile.html",
            current_user=user, error="昵称长度需在 1–64 字符之间",
            status_code=400,
        )
    user.nickname = nickname
    db.commit()
    return render(
        request, "me/profile.html",
        current_user=user, message="已保存",
    )
