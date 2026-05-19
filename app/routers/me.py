"""Personal center: profile, signin, my-requests, recent ledger."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import DailySignin, HelpRequest, PointTransaction, User
from ..points import REASON_SIGNIN, adjust_points
from ..runtime_config import as_int, get_setting
from ..security import require_csrf, require_login
from ..settings import settings
from ..templating import render
from ..timekit import today_cn_str
from ..urls import redirect

router = APIRouter(tags=["me"])


def _me_context(db: Session, user: User) -> dict:
    """Build the data the /me dashboard needs (also reused after signin)."""
    today = today_cn_str()
    signed_today = db.scalar(
        select(DailySignin.id).where(
            DailySignin.user_id == user.id, DailySignin.date == today,
        )
    ) is not None

    my_requests = db.scalars(
        select(HelpRequest)
        .where(HelpRequest.requester_id == user.id)
        .order_by(desc(HelpRequest.created_at))
        .limit(10)
    ).all()

    my_helps = db.scalars(
        select(HelpRequest)
        .where(HelpRequest.claimed_by == user.id)
        .order_by(desc(HelpRequest.claimed_at))
        .limit(10)
    ).all()

    recent_tx = db.scalars(
        select(PointTransaction)
        .where(PointTransaction.user_id == user.id)
        .order_by(desc(PointTransaction.created_at))
        .limit(8)
    ).all()

    signin_points = get_setting(db, "SIGNIN_POINTS", settings.SIGNIN_POINTS, cast=as_int)

    return {
        "signed_today": signed_today,
        "signin_points": signin_points,
        "my_requests": my_requests,
        "my_helps": my_helps,
        "recent_tx": recent_tx,
    }


@router.get("/me")
def me_index(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    return render(request, "me/index.html", current_user=user, **_me_context(db, user))


@router.post("/me/signin")
def signin(
    request: Request,
    _csrf: None = Depends(require_csrf),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    today = today_cn_str()
    existing = db.scalar(
        select(DailySignin.id).where(
            DailySignin.user_id == user.id, DailySignin.date == today,
        )
    )
    if existing is None:
        signin_points = get_setting(db, "SIGNIN_POINTS", settings.SIGNIN_POINTS, cast=as_int)
        db.add(DailySignin(user_id=user.id, date=today))
        adjust_points(
            db, user.id, signin_points, REASON_SIGNIN, note=f"daily {today}",
        )
        db.commit()
    return redirect(request, "/me")


@router.get("/me/profile")
def profile_form(request: Request, user: User = Depends(require_login)):
    return render(request, "me/profile.html", current_user=user)


@router.post("/me/profile")
def profile_submit(
    request: Request,
    nickname: str = Form(...),
    _csrf: None = Depends(require_csrf),
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
