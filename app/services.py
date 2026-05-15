"""State-machine helpers for HelpRequest + library deduplication.

The same functions back the manual endpoints (confirm/reject) AND the
APScheduler tick (auto-confirm after 48h, expire after 7d). Keeping them
here ensures both code paths produce identical side-effects in points
ledger / library / status transitions.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .models import Attachment, HelpRequest, LibraryPaper
from .pdf_redact import safe_desensitize
from .points import (
    REASON_HELP_ACCEPTED,
    REASON_PUBLISH_REFUND_TIMEOUT,
    adjust_points,
)
from .timekit import now_utc_naive


logger = logging.getLogger("lit-share.services")

ROOT = Path(__file__).resolve().parent.parent
UPLOADS_DIR = ROOT / "uploads"
LIBRARY_DIR = ROOT / "library"
UPLOADS_DIR.mkdir(exist_ok=True)
LIBRARY_DIR.mkdir(exist_ok=True)


def _normalize(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def find_library_match(db: Session, title: str, authors: str, year: int) -> Optional[LibraryPaper]:
    """Lookup an existing library entry by normalized title+authors+year.

    This is intentionally coarse — typo-tolerant matching (Levenshtein, etc.)
    would be nicer but overkill for MVP. Admin can dedupe manually if needed."""
    title_n = _normalize(title)
    authors_n = _normalize(authors)
    return db.scalar(
        select(LibraryPaper).where(
            func.lower(LibraryPaper.title) == title_n,
            func.lower(LibraryPaper.authors) == authors_n,
            LibraryPaper.year == year,
        )
    )


def latest_attachment(db: Session, req_id: int) -> Optional[Attachment]:
    return db.scalar(
        select(Attachment)
        .where(Attachment.request_id == req_id)
        .order_by(desc(Attachment.uploaded_at))
        .limit(1)
    )


def library_files(paper: LibraryPaper) -> tuple[Path, Path]:
    """Return (original, sanitized) paths for a paper. Convention-based:
    library/{id}.pdf and library/{id}.sanitized.pdf alongside."""
    orig = Path(paper.file_path)
    sani = orig.with_name(f"{orig.stem}.sanitized{orig.suffix}")
    return orig, sani


def complete_request(db: Session, req: HelpRequest) -> None:
    """Mark a request completed: pay helper, sink to library. Idempotent.

    Caller must commit. Used by both manual /confirm and the auto-confirm tick."""
    if req.status == "completed":
        return
    if req.status != "awaiting_confirm":
        raise ValueError(f"req {req.id}: can't complete from status={req.status}")
    if req.claimed_by is None:
        raise ValueError(f"req {req.id}: no claimer to pay")

    adjust_points(
        db, req.claimed_by, req.bounty, REASON_HELP_ACCEPTED,
        ref_request_id=req.id,
        note=f"helper for #{req.id}",
    )

    paper = find_library_match(db, req.title, req.authors, req.year)
    if paper is None:
        att = latest_attachment(db, req.id)
        if att is None:
            raise RuntimeError(f"req {req.id} awaiting_confirm but has no attachment")
        paper = LibraryPaper(
            title=req.title, authors=req.authors,
            journal=req.journal, year=req.year,
            file_path="",
        )
        db.add(paper)
        db.flush()  # get paper.id

        dst_orig = LIBRARY_DIR / f"{paper.id}.pdf"
        dst_sani = LIBRARY_DIR / f"{paper.id}.sanitized.pdf"
        shutil.copyfile(att.original_path, dst_orig)
        if att.sanitized_path and Path(att.sanitized_path).exists():
            shutil.copyfile(att.sanitized_path, dst_sani)
        else:
            # Lazy-generate sanitized variant for the library
            safe_desensitize(str(dst_orig), str(dst_sani))
        paper.file_path = str(dst_orig)
        logger.info("library: new paper %d (%s)", paper.id, req.title[:60])
    else:
        logger.info("library: dedupe hit, req #%d -> paper #%d", req.id, paper.id)

    req.library_paper_id = paper.id
    req.status = "completed"
    req.completed_at = now_utc_naive()


def expire_request(db: Session, req: HelpRequest) -> None:
    """Mark unworked request expired and refund the bounty. Idempotent. Caller commits."""
    if req.status == "expired":
        return
    if req.status != "open":
        raise ValueError(f"req {req.id}: can't expire from status={req.status}")
    adjust_points(
        db, req.requester_id, req.bounty, REASON_PUBLISH_REFUND_TIMEOUT,
        ref_request_id=req.id,
        note=f"timeout refund #{req.id}",
        allow_negative=True,  # admin may have clawed back; let it go negative gracefully
    )
    req.status = "expired"
    req.completed_at = now_utc_naive()
    logger.info("expired req #%d (refund %d to user %d)", req.id, req.bounty, req.requester_id)


def reject_upload(db: Session, req: HelpRequest, reason: str = "") -> None:
    """Requester rejects the upload: send back to `open` so another helper can pick it up.

    The previous attachment row stays for audit. The previous helper loses claim.
    Caller commits."""
    if req.status != "awaiting_confirm":
        raise ValueError(f"req {req.id}: can't reject from status={req.status}")
    logger.info("rejected req #%d (helper %s): %s", req.id, req.claimed_by, reason or "(no reason)")
    req.status = "open"
    req.claimed_by = None
    req.claimed_at = None
    req.uploaded_at = None
    req.confirm_deadline = None


def tick(db: Session) -> dict:
    """Periodic state advance. Returns counters for logging.
    Safe to call from a background scheduler; commits internally."""
    now = now_utc_naive()
    counters = {"expired": 0, "auto_confirmed": 0, "errors": 0}

    expired = db.scalars(
        select(HelpRequest).where(
            HelpRequest.status == "open",
            HelpRequest.request_deadline < now,
        )
    ).all()
    for req in expired:
        try:
            expire_request(db, req)
            counters["expired"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("tick: expire_request failed for req %d", req.id)
            counters["errors"] += 1
            db.rollback()

    confirmable = db.scalars(
        select(HelpRequest).where(
            HelpRequest.status == "awaiting_confirm",
            HelpRequest.confirm_deadline < now,
        )
    ).all()
    for req in confirmable:
        try:
            complete_request(db, req)
            counters["auto_confirmed"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("tick: auto_confirm failed for req %d", req.id)
            counters["errors"] += 1
            db.rollback()

    if counters["expired"] + counters["auto_confirmed"] > 0:
        db.commit()
    return counters
