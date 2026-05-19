"""Jinja2 templates + render helper that injects globals every page needs."""
from pathlib import Path
from typing import Any, Optional

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .db import SessionLocal
from .models import User
from .runtime_config import get_setting
from .security import CSRF_COOKIE, ensure_csrf_token, set_csrf_cookie
from .settings import settings


_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _runtime_site_text() -> tuple[str, str]:
    """Read runtime-overridable site copy with a safe fallback to .env defaults."""
    db = SessionLocal()
    try:
        site_title = get_setting(db, "SITE_TITLE", settings.SITE_TITLE)
        site_slogan = get_setting(db, "SITE_SLOGAN", settings.SITE_SLOGAN)
        return site_title, site_slogan
    except Exception:  # noqa: BLE001
        return settings.SITE_TITLE, settings.SITE_SLOGAN
    finally:
        db.close()


def base_path_of(request: Request) -> str:
    """The public URL prefix the browser sees for this request.

    Derived from X-Forwarded-Prefix (set by Caddy per-site), so the same
    uvicorn instance can be served at multiple public bases — e.g.
    `c.xpro.work/preview/lit/*` AND `hz.xpro.work/*` simultaneously.
    """
    return request.scope.get("root_path", "") or ""


def render(
    request: Request,
    template: str,
    current_user: Optional[User] = None,
    status_code: int = 200,
    **context: Any,
):
    site_title, site_slogan = _runtime_site_text()
    context.setdefault("site_title", site_title)
    context.setdefault("site_slogan", site_slogan)
    context["base_path"] = base_path_of(request)
    context["current_user"] = current_user
    csrf_token = ensure_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        template,
        {"request": request, **context, "csrf_token": csrf_token},
        status_code=status_code,
    )
    if request.cookies.get(CSRF_COOKIE) != csrf_token:
        set_csrf_cookie(response, request, csrf_token)
    return response
