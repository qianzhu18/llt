"""FastAPI entry. Mounts routers and serves the homepage."""
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .db import Base, engine
from .models import User
from .routers import auth as auth_router
from .routers import me as me_router
from .security import current_user
from .settings import settings
from .templating import render


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
    root_path=settings.APP_BASE_PATH,  # behind Caddy; tells FastAPI its public prefix
)

app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")

app.include_router(auth_router.router)
app.include_router(me_router.router)


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    """Redirect unauthenticated HTML GETs to login; otherwise fall through."""
    if (
        exc.status_code == status.HTTP_401_UNAUTHORIZED
        and exc.detail == "login_required"
        and "text/html" in request.headers.get("accept", "")
    ):
        next_path = request.url.path
        target = (settings.APP_BASE_PATH or "") + f"/auth/login?next={next_path}"
        return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
    # Default handling for everything else.
    from fastapi.exception_handlers import http_exception_handler
    return await http_exception_handler(request, exc)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2.0-m1"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, user: Optional[User] = Depends(current_user)):
    return render(request, "index.html", current_user=user)
