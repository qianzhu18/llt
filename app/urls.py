"""Per-request URL helpers. Single source of truth for base-path-aware redirects."""
from fastapi import Request, status
from fastapi.responses import RedirectResponse


def base_path_of(request: Request) -> str:
    """The public URL prefix the browser sees for this request.

    Derived from X-Forwarded-Prefix (set by Caddy per-site), so the same
    uvicorn instance can be served at multiple public bases.
    """
    return request.scope.get("root_path", "") or ""


def public_url(request: Request, path: str) -> str:
    """Prefix an internal path with this request's public base (or '/' for root)."""
    base = base_path_of(request)
    if not path.startswith("/"):
        path = "/" + path
    return (base + path) or "/"


def redirect(request: Request, path: str, status_code: int = status.HTTP_303_SEE_OTHER) -> RedirectResponse:
    return RedirectResponse(url=public_url(request, path), status_code=status_code)


def strip_base(request: Request, public_path: str) -> str:
    """Given a public path like '/preview/lit/me', return the internal '/me'.
    Used to validate ?next= redirect targets against same-origin."""
    base = base_path_of(request)
    if not public_path or not public_path.startswith("/"):
        return ""
    if not base:
        return public_path
    if public_path == base:
        return "/"
    if public_path.startswith(base + "/"):
        return public_path[len(base):]
    return ""
