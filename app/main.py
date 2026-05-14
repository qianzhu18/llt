"""FastAPI entry. M0: scaffold with health check + index placeholder + reverse-proxy-aware URLs."""
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import Base, engine
from .settings import settings


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = ROOT / "uploads"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)


# On first run, create tables. Real schema changes will use Alembic.
from . import models  # noqa: F401  (register mappers)
Base.metadata.create_all(bind=engine)


app = FastAPI(
    title=settings.SITE_TITLE,
    docs_url="/api-docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    root_path=settings.APP_BASE_PATH,  # behind Caddy strip_prefix; this tells FastAPI its public prefix
)

templates = Jinja2Templates(directory=str(ROOT / "app" / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0-m0"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "site_title": settings.SITE_TITLE,
            "site_slogan": settings.SITE_SLOGAN,
            "base_path": settings.APP_BASE_PATH,
        },
    )
