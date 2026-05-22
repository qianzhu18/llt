"""JSON API homepage data endpoint for the Vue SPA."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import HelpRequest, LibraryPaper, PointTransaction, User
from ...points import REASON_HELP_ACCEPTED, REASON_PUBLISH_DEDUCT
from ...runtime_config import get_setting
from ...settings import settings

router = APIRouter(prefix="/api/v1", tags=["api-home"])


def _recent_activities(db: Session, limit: int = 15) -> list[dict]:
    rows = db.execute(
        select(PointTransaction, User.nickname, HelpRequest.title)
        .join(User, User.id == PointTransaction.user_id)
        .join(HelpRequest, HelpRequest.id == PointTransaction.ref_request_id, isouter=True)
        .where(PointTransaction.reason.in_([REASON_PUBLISH_DEDUCT, REASON_HELP_ACCEPTED]))
        .order_by(desc(PointTransaction.created_at))
        .limit(limit)
    ).all()
    out = []
    for tx, nick, title in rows:
        if tx.reason == REASON_PUBLISH_DEDUCT:
            out.append({"actor": nick, "verb": "求助了", "object": title or "?", "ts": tx.created_at.isoformat()})
        elif tx.reason == REASON_HELP_ACCEPTED:
            out.append({"actor": nick, "verb": "完成了一次应助", "object": "", "ts": tx.created_at.isoformat()})
    return out


def _recent_library(db: Session, limit: int = 6) -> list[dict]:
    papers = db.scalars(
        select(LibraryPaper).order_by(desc(LibraryPaper.created_at)).limit(limit)
    ).all()
    return [
        {
            "id": p.id,
            "title": p.title,
            "authors": p.authors,
            "journal": p.journal,
            "year": p.year,
            "download_count": p.download_count,
        }
        for p in papers
    ]


@router.get("/home")
def home_data(db: Session = Depends(get_db)):
    return {
        "activities": _recent_activities(db),
        "recent_library": _recent_library(db),
        "library_count": db.scalar(select(func.count(LibraryPaper.id))) or 0,
        "site_title": get_setting(db, "SITE_TITLE", settings.SITE_TITLE),
        "site_slogan": get_setting(db, "SITE_SLOGAN", settings.SITE_SLOGAN),
    }


@router.get("/search")
def search(q: str = Query("", min_length=1, max_length=200), db: Session = Depends(get_db)):
    like = f"%{q.lower()}%"
    limit = 5

    lib_cond = or_(
        func.lower(LibraryPaper.title).like(like),
        func.lower(LibraryPaper.authors).like(like),
        func.lower(LibraryPaper.journal).like(like),
    )
    library_results = db.scalars(
        select(LibraryPaper).where(lib_cond).order_by(desc(LibraryPaper.created_at)).limit(limit)
    ).all()

    req_cond = or_(
        func.lower(HelpRequest.title).like(like),
        func.lower(HelpRequest.authors).like(like),
        func.lower(HelpRequest.journal).like(like),
    )
    open_req_results = db.scalars(
        select(HelpRequest)
        .where(HelpRequest.status == "open", req_cond)
        .order_by(desc(HelpRequest.created_at))
        .limit(limit)
    ).all()

    return {
        "library_results": [
            {"id": p.id, "title": p.title, "authors": p.authors, "journal": p.journal, "year": p.year}
            for p in library_results
        ],
        "open_req_results": [
            {"id": r.id, "title": r.title, "authors": r.authors, "year": r.year}
            for r in open_req_results
        ],
    }
