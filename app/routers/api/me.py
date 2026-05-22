"""JSON API personal center endpoints for the Vue SPA."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import DailySignin, HelpRequest, PointTransaction, User
from ...points import REASON_SIGNIN, adjust_points
from ...runtime_config import as_int, get_setting
from ...security import require_csrf_header, require_login
from ...settings import settings
from ...timekit import today_cn_str

router = APIRouter(prefix="/api/v1/me", tags=["api-me"])

REASON_LABELS = {
    "signin": "每日签到",
    "publish_deduct": "发布求助扣积分",
    "publish_refund_timeout": "超时退款",
    "publish_refund_closed": "关闭退款",
    "help_accepted": "应助获得积分",
    "admin_gift": "管理员赠送",
}


def _tx_json(tx: PointTransaction) -> dict:
    return {
        "id": tx.id,
        "delta": tx.delta,
        "reason": tx.reason,
        "reason_label": REASON_LABELS.get(tx.reason, tx.reason),
        "note": tx.note,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
    }


def _req_json(req: HelpRequest) -> dict:
    return {
        "id": req.id,
        "title": req.title,
        "status": req.status,
        "bounty": req.bounty,
        "created_at": req.created_at.isoformat() if req.created_at else None,
    }


@router.get("")
def me_dashboard(
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
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

    my_requests_count = db.scalar(
        select(func.count(HelpRequest.id)).where(HelpRequest.requester_id == user.id)
    ) or 0
    my_helps_count = db.scalar(
        select(func.count(HelpRequest.id)).where(HelpRequest.claimed_by == user.id)
    ) or 0
    tx_count = db.scalar(
        select(func.count(PointTransaction.id)).where(PointTransaction.user_id == user.id)
    ) or 0

    return {
        "points": user.points,
        "signed_today": signed_today,
        "my_requests_count": my_requests_count,
        "my_helps_count": my_helps_count,
        "tx_count": tx_count,
        "my_requests": [_req_json(r) for r in my_requests],
        "my_helps": [_req_json(r) for r in my_helps],
        "transactions": [_tx_json(tx) for tx in recent_tx],
    }


@router.post("/signin")
def signin(
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    today = today_cn_str()
    existing = db.scalar(
        select(DailySignin.id).where(
            DailySignin.user_id == user.id, DailySignin.date == today,
        )
    )
    if existing is not None:
        return JSONResponse({"detail": "今天已经签到过了"}, status_code=400)

    signin_points = get_setting(db, "SIGNIN_POINTS", settings.SIGNIN_POINTS, cast=as_int)
    db.add(DailySignin(user_id=user.id, date=today))
    adjust_points(db, user.id, signin_points, REASON_SIGNIN, note=f"daily {today}")
    db.commit()

    return {"ok": True, "points_awarded": signin_points, "message": f"签到成功，获得 {signin_points} 积分"}


class ProfileBody(BaseModel):
    nickname: str


@router.post("/profile")
def update_profile(
    body: ProfileBody,
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    nickname = body.nickname.strip()
    if not (1 <= len(nickname) <= 64):
        return JSONResponse({"detail": "昵称长度需在 1–64 字符之间"}, status_code=400)
    user.nickname = nickname
    db.commit()
    return {"ok": True, "nickname": nickname}
