"""Jinja2 templates + render helper that injects globals every page needs."""
from pathlib import Path
from typing import Any, Optional

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .models import User
from .settings import settings


_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def render(
    request: Request,
    template: str,
    current_user: Optional[User] = None,
    status_code: int = 200,
    **context: Any,
):
    context.setdefault("site_title", settings.SITE_TITLE)
    context.setdefault("site_slogan", settings.SITE_SLOGAN)
    context["base_path"] = settings.APP_BASE_PATH
    context["current_user"] = current_user
    return templates.TemplateResponse(template, {"request": request, **context}, status_code=status_code)
