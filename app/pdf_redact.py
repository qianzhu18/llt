"""Best-effort PDF de-identification using PyMuPDF.

Two passes:
1. Clear standard PDF metadata (title/author/subject/keywords/producer/creator) —
   the most reliable PII vector since these fields often leak the author's
   institutional account name.
2. On the first and last page (where affiliations & corresponding-author
   contact info typically live), search for email-address & IPv4 patterns,
   then apply PDF redaction annotations to permanently overwrite the matched
   regions with black rectangles before saving with `garbage=4` (drops
   orphaned objects, so redacted bytes aren't recoverable from the PDF stream).

Caveats: search_for() does literal text matching after PyMuPDF re-flows the
glyph stream. If a redaction target is broken across lines or hyphenated,
this won't catch it. Treat this as defense-in-depth, not a guarantee.
M4 can add OCR pass / wider scanning if needed.
"""
from __future__ import annotations

import re
from typing import Optional

import fitz  # PyMuPDF


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IPV4_RE = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")


def desensitize_pdf(in_path: str, out_path: str) -> dict:
    """De-identify a PDF in place at out_path. Returns counters for logs."""
    doc = fitz.open(in_path)
    try:
        stats = {"pages": len(doc), "emails": 0, "ips": 0, "metadata_cleared": True}

        # Pass 1: nuke metadata. set_metadata({}) is the documented "clear" form.
        doc.set_metadata({})

        # Pass 2: redact PII matches on first & last page only — this is where
        # affiliation footers / corresponding-author boxes usually live, and
        # scanning every page on a 50MB PDF would be too slow on a 1-core VM.
        pages = []
        if len(doc) >= 1:
            pages.append(0)
        if len(doc) > 1 and len(doc) - 1 not in pages:
            pages.append(len(doc) - 1)

        for pno in pages:
            page = doc[pno]
            text = page.get_text() or ""
            for pattern, key in ((_EMAIL_RE, "emails"), (_IPV4_RE, "ips")):
                seen: set[str] = set()
                for m in pattern.finditer(text):
                    hit = m.group()
                    if hit in seen:
                        continue
                    seen.add(hit)
                    for rect in page.search_for(hit):
                        page.add_redact_annot(rect, fill=(0, 0, 0))
                        stats[key] += 1
            page.apply_redactions()

        doc.save(out_path, garbage=4, deflate=True)
        return stats
    finally:
        doc.close()


def safe_desensitize(in_path: str, out_path: str) -> Optional[dict]:
    """Wrapped variant that returns None on failure instead of raising — for
    upload flows where a malformed PDF shouldn't 500 the whole request."""
    try:
        return desensitize_pdf(in_path, out_path)
    except Exception:  # noqa: BLE001
        return None
