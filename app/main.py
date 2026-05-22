"""FastAPI entry. Mounts JSON API routers, starts the background scheduler."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import Base, SessionLocal, engine
from .routers.api import admin as api_admin_router
from .routers.api import auth as api_auth_router
from .routers.api import home as api_home_router
from .routers.api import library as api_library_router
from .routers.api import me as api_me_router
from .routers.api import requests as api_requests_router
from .security import CSRF_COOKIE, ensure_csrf_token, set_csrf_cookie
from .services import tick
from .settings import settings


# Send our app loggers to stderr so they land in systemd's journal / app.log.
# Avoid touching root config so we don't fight with uvicorn's own logging.
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
_app_logger = logging.getLogger("lit-share")
_app_logger.setLevel(logging.INFO)
if not _app_logger.handlers:
    _app_logger.addHandler(_handler)
_app_logger.propagate = False

logger = logging.getLogger("lit-share.main")


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = ROOT / "uploads"
DEPLOY_BRANCH_FILE = ROOT / ".deploy_branch"
DEPLOY_REV_FILE = ROOT / ".deploy_rev"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)


# On first run, create tables. Real schema changes will use Alembic.
from . import models  # noqa: F401  (register mappers)
Base.metadata.create_all(bind=engine)


def _scheduled_tick():
    """Periodic state advance. Runs in APScheduler's thread pool, opens a
    fresh session, never raises (errors are logged)."""
    db = SessionLocal()
    try:
        result = tick(db)
        if result["expired"] or result["auto_confirmed"]:
            logger.info("tick: %s", result)
    except Exception:  # noqa: BLE001
        logger.exception("scheduled tick failed")
    finally:
        db.close()


_scheduler = BackgroundScheduler(daemon=True, timezone="UTC")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _scheduler.add_job(
        _scheduled_tick, "interval",
        seconds=60, id="tick",
        coalesce=True, max_instances=1,
        next_run_time=None,
    )
    _scheduler.start()
    logger.info("scheduler started (tick interval=60s)")
    try:
        yield
    finally:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler stopped")


app = FastAPI(
    title=settings.SITE_TITLE,
    docs_url="/api-docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)


@app.middleware("http")
async def proxy_prefix(request: Request, call_next):
    """Caddy tells us the public base path per site via X-Forwarded-Prefix.
    This lets the same uvicorn instance serve `c.xpro.work/preview/lit/*` AND
    `hz.xpro.work/*` with correct cookie path / template URLs / redirects."""
    fwd = request.headers.get("x-forwarded-prefix")
    if fwd is not None:
        request.scope["root_path"] = fwd.rstrip("/")
    return await call_next(request)


@app.middleware("http")
async def ensure_csrf(request: Request, call_next):
    """Ensure every response carries a valid CSRF cookie (non-httponly for SPA)."""
    response = await call_next(request)
    if CSRF_COOKIE not in request.cookies or not request.cookies.get(CSRF_COOKIE):
        token = ensure_csrf_token(request)
        set_csrf_cookie(response, request, token)
    return response


# JSON API routers for the Vue SPA
app.include_router(api_auth_router.router)
app.include_router(api_home_router.router)
app.include_router(api_requests_router.router)
app.include_router(api_library_router.router)
app.include_router(api_me_router.router)
app.include_router(api_admin_router.router)


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    """Default HTTP exception handling."""
    from fastapi.exception_handlers import http_exception_handler
    return await http_exception_handler(request, exc)


@app.get("/health")
def health():
    branch = DEPLOY_BRANCH_FILE.read_text(encoding="utf-8").strip() if DEPLOY_BRANCH_FILE.exists() else ""
    rev = DEPLOY_REV_FILE.read_text(encoding="utf-8").strip() if DEPLOY_REV_FILE.exists() else ""
    return {
        "status": "ok",
        "version": rev[:7] if rev else "workspace",
        "deploy_branch": branch or None,
        "deploy_rev": rev or None,
    }



# ---------------------------------------------------------------------------
# Serve Vue SPA in production (frontend/dist)
# ---------------------------------------------------------------------------
_FRONTEND_DIST = ROOT / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    from starlette.middleware.base import BaseHTTPMiddleware

    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="vue-assets")

    class VueSpaFallback(BaseHTTPMiddleware):
        """If no API/static route matched AND the path looks like a SPA route
        (no file extension), serve Vue's index.html. Otherwise 404 as usual."""
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            if response.status_code == 404:
                path = request.url.path
                # Skip API and static paths
                if path.startswith("/api/") or path.startswith("/static/") or path.startswith("/assets/"):
                    return response
                # Skip paths with file extensions (e.g. favicon.ico, robots.txt)
                if "." in path.split("/")[-1]:
                    return response
                # Serve Vue index.html for SPA routes
                index = _FRONTEND_DIST / "index.html"
                if index.is_file():
                    spa_resp = FileResponse(str(index))
                    # Propagate cookies set by earlier middleware (e.g. CSRF)
                    for key, value in response.headers.multi_items():
                        if key.lower() == "set-cookie":
                            spa_resp.headers.append(key, value)
                    return spa_resp
            return response

    app.add_middleware(VueSpaFallback)
