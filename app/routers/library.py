"""Shared library browsing + download."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import LibraryPaper, User
from ..runtime_config import as_bool, get_setting
from ..security import current_user, require_login
from ..services import library_files
from ..settings import settings
from ..templating import render


router = APIRouter(prefix="/library", tags=["library"])

PAGE_SIZE = 20


@router.get("")
def index(
    request: Request,
    q: str = Query(""),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(current_user),
):
    q = q.strip()
    base_stmt = select(LibraryPaper)
    count_stmt = select(func.count(LibraryPaper.id))

    if q:
        like = f"%{q.lower()}%"
        matched = or_(
            func.lower(LibraryPaper.title).like(like),
            func.lower(LibraryPaper.authors).like(like),
            func.lower(LibraryPaper.journal).like(like),
        )
        base_stmt = base_stmt.where(matched)
        count_stmt = count_stmt.where(matched)

    total = db.scalar(count_stmt) or 0
    offset = (page - 1) * PAGE_SIZE
    items = db.scalars(
        base_stmt.order_by(desc(LibraryPaper.created_at)).offset(offset).limit(PAGE_SIZE)
    ).all()
    has_next = offset + len(items) < total

    return render(
        request,
        "library/index.html",
        current_user=viewer,
        items=items,
        q=q,
        total=total,
        page=page,
        has_next=has_next,
    )


@router.get("/{paper_id}/download")
def download(
    paper_id: int,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    paper = db.get(LibraryPaper, paper_id)
    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    want_sani = get_setting(
        db, "PDF_DESENSITIZE_ENABLED", settings.PDF_DESENSITIZE_ENABLED, cast=as_bool,
    )
    orig, sani = library_files(paper)
    file_path = sani if (want_sani and sani.exists()) else orig

    if not Path(file_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    paper.download_count += 1
    db.commit()

    return FileResponse(
        str(file_path),
        media_type="application/pdf",
        filename=f"library-{paper.id}.pdf",
    )
