"""SMTP sender. Reads runtime_config first (admin-editable), falls back to .env.

Design choices:
- Never raises. SMTP failures (auth rejection / timeout / DNS) fall back to a log
  warning with the verify link, so registration never 500s on email infra hiccups.
- Synchronous send. For demo throughput this is fine; if registration rate
  becomes a bottleneck, move sends to a thread pool or background job.

Security note: SMTP_PASS is stored in the system_settings table as plaintext
(an explicit user-facing requirement: admins set it via /admin/settings).
On a single-server demo VM, anyone with DB access can already read all data;
treat this as acceptable for this deployment tier. M5/M6 may want a secrets
manager or encrypted column.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import TypedDict

from sqlalchemy.orm import Session

from .runtime_config import as_bool, as_int, get_setting
from .settings import settings


logger = logging.getLogger("lit-share.email")


class SendResult(TypedDict):
    mode: str           # "smtp" | "log" | "error"
    detail: str


def _smtp_config(db: Session) -> dict:
    return {
        "host":     get_setting(db, "SMTP_HOST", settings.SMTP_HOST),
        "port":     get_setting(db, "SMTP_PORT", settings.SMTP_PORT, cast=as_int),
        "user":     get_setting(db, "SMTP_USER", settings.SMTP_USER),
        "password": get_setting(db, "SMTP_PASS", settings.SMTP_PASS),
        "from":     get_setting(db, "SMTP_FROM", settings.SMTP_FROM),
        "use_ssl":  get_setting(db, "SMTP_USE_SSL", settings.SMTP_USE_SSL, cast=as_bool),
    }


def smtp_status(db: Session) -> dict:
    cfg = _smtp_config(db)
    return {
        "configured": bool(cfg["host"]),
        "host": cfg["host"],
        "port": cfg["port"],
        "user": cfg["user"],
        "from_addr": cfg["from"] or cfg["user"] or "noreply@xpro.work",
        "use_ssl": bool(cfg["use_ssl"]),
        "password_set": bool(cfg["password"]),
    }


def send_email(db: Session, *, to: str, subject: str, body: str) -> SendResult:
    """Best-effort plain-text email delivery using the configured SMTP transport."""
    cfg = _smtp_config(db)

    if not cfg["host"]:
        logger.warning("== EMAIL STUB (no SMTP_HOST) ==> to=%s subject=%s", to, subject)
        return {"mode": "log", "detail": "SMTP_HOST 未配置"}

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from"] or cfg["user"] or "noreply@xpro.work"
    msg["To"] = to
    msg.set_content(body)

    try:
        if cfg["use_ssl"]:
            smtp = smtplib.SMTP_SSL(cfg["host"], cfg["port"] or 465, timeout=15)
        else:
            smtp = smtplib.SMTP(cfg["host"], cfg["port"] or 587, timeout=15)
            smtp.starttls()
        try:
            if cfg["user"] and cfg["password"]:
                smtp.login(cfg["user"], cfg["password"])
            smtp.send_message(msg)
        finally:
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001
                pass
        logger.info("email sent via SMTP host=%s to=%s subject=%s", cfg["host"], to, subject)
        return {"mode": "smtp", "detail": "ok"}
    except Exception as e:  # noqa: BLE001
        logger.exception("SMTP send failed for %s, falling back to log stub", to)
        logger.warning("== EMAIL STUB (SMTP fail) ==> to=%s subject=%s", to, subject)
        return {"mode": "error", "detail": str(e)[:200]}


def send_verify_email(db: Session, to: str, verify_link: str, site_title: str) -> SendResult:
    """Deliver the email-verification link. Returns a SendResult describing
    which path was taken; callers can choose the user-facing copy accordingly."""
    result = send_email(
        db,
        to=to,
        subject=f"[{site_title}] 验证你的邮箱",
        body=(
            f"你好，\n\n"
            f"感谢注册「{site_title}」。请点击下方链接完成邮箱验证（24 小时内有效）：\n\n"
            f"{verify_link}\n\n"
            f"如果你没有注册过我们的网站，请忽略此邮件。\n\n"
            f"—— {site_title}\n"
        ),
    )
    if result["mode"] == "smtp":
        logger.info("verify email sent via SMTP to=%s", to)
    return result
