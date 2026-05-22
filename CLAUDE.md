# 公益文献互助 (ScholarAid)

## Architecture

**Frontend**: Vue 3 + Vite + TypeScript + Tailwind CSS + Pinia + Vue Router (`frontend/`)
**Backend**: FastAPI + SQLAlchemy + Jinja2 (legacy) + SQLite (`app/`)
**Deployment**: FastAPI serves both JSON API (`/api/v1/*`) and Vue SPA static files

### Development

```bash
# Terminal 1: FastAPI backend
cd /path/to/project && .venv/bin/python -m uvicorn app.main:app --reload --port 10800

# Terminal 2: Vue dev server (proxies /api → :10800)
cd frontend && npm install && npm run dev
```

### Production

```bash
cd frontend && npm run build   # produces frontend/dist/
# FastAPI auto-serves frontend/dist/ when it exists (SPA fallback middleware)
```

### API Routes (under /api/v1/)

- `GET /api/v1/auth/me` — current user or 401
- `POST /api/v1/auth/register` — {email, nickname, password}
- `POST /api/v1/auth/login` — {email, password} → sets session cookie
- `POST /api/v1/auth/logout` — clears session cookie
- `GET /api/v1/home` — homepage data (activities, library, stats)
- `GET /api/v1/search?q=` — search library + open requests

### Auth

- Signed cookie session (`litshare_session`, httponly, 30 days)
- CSRF: double-submit cookie (`litshare_csrf`, **non-httponly** for SPA), validated via `X-CSRF-Token` header
- API endpoints use `require_csrf_header` dependency; Jinja2 routes use `require_csrf` (form field)

### Key Files

- `app/main.py` — entry point, router mounting, SPA fallback middleware
- `app/security.py` — auth primitives (bcrypt, session, CSRF, deps)
- `app/models.py` — SQLAlchemy models (users, help_requests, library_papers, etc.)
- `app/services.py` — state machine (complete/expire/reject/tick)
- `app/routers/api/` — JSON API endpoints for Vue SPA
- `frontend/src/stores/auth.ts` — Pinia auth store
- `frontend/src/api/client.ts` — axios with CSRF + 401 redirect
- `frontend/src/router/index.ts` — Vue Router with auth guards

## Migration Status

**Sprint 0 (done)**: Vue scaffold + auth API + homepage data API + all page stubs
**Sprint 1 (next)**: Requests API (lobby/detail/create/actions) + full Vue pages
**Sprint 2**: Library/Me/Admin API + full Vue pages
**Sprint 3**: Remove Jinja2 templates, final cleanup

## Business Rules

- Points system: publish deducts bounty, completion pays helper, timeout refunds
- Request status: open → claimed → awaiting_confirm → completed (also: expired, closed)
- PDF redaction: metadata cleared, email/IP blacked out on first/last pages
- Rate limits: max 3 active requests, same-journal monthly limit, report threshold
- Background scheduler (APScheduler): auto-expires overdue requests, auto-confirms overdue claims
