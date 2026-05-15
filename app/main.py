"""FastAPI entry. Mounts routers, starts the background scheduler, serves the homepage."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .db import Base, SessionLocal, engine, get_db
from .models import HelpRequest, PointTransaction, User
from .points import REASON_HELP_ACCEPTED, REASON_PUBLISH_DEDUCT
from .routers import admin as admin_router
from .routers import auth as auth_router
from .routers import me as me_router
from .routers import requests as requests_router
from .security import current_user
from .services import tick
from .settings import settings
from .templating import render


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


app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")

app.include_router(auth_router.router)
app.include_router(me_router.router)
app.include_router(requests_router.router)
app.include_router(admin_router.router)


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    """Redirect unauthenticated HTML GETs to login; otherwise fall through."""
    if (
        exc.status_code == status.HTTP_401_UNAUTHORIZED
        and exc.detail == "login_required"
        and "text/html" in request.headers.get("accept", "")
    ):
        from .urls import public_url
        base = request.scope.get("root_path", "")
        # next= must include the public base so post-login round-trip works.
        public_next = base + request.url.path
        return RedirectResponse(
            url=public_url(request, f"/auth/login?next={public_next}"),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    # Default handling for everything else.
    from fastapi.exception_handlers import http_exception_handler
    return await http_exception_handler(request, exc)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.5.0-m4"}


def _recent_activities(db: Session, limit: int = 15) -> list[dict]:
    """Recent publish + accept events for the homepage ticker."""
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
            out.append({"actor": nick, "verb": "求助了", "object": title or "?", "ts": tx.created_at})
        elif tx.reason == REASON_HELP_ACCEPTED:
            out.append({"actor": nick, "verb": "完成了一次应助", "object": "", "ts": tx.created_at})
    return out


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    user: Optional[User] = Depends(current_user),
    db: Session = Depends(get_db),
):
    return render(
        request, "index.html",
        current_user=user,
        activities=_recent_activities(db),
    )
