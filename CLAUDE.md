# 公益文献互助 (ScholarAid)

## Architecture

**Frontend**: Vue 3 + Vite + TypeScript + Tailwind CSS + Pinia + Vue Router (`frontend/`)
**Backend**: FastAPI + SQLAlchemy + SQLite (`app/`)
**Deployment**: FastAPI serves JSON API (`/api/v1/*`) + Vue SPA static files from `frontend/dist/`

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

- **Auth**: `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/resend-verify`
- **Home**: `GET /home`, `GET /search?q=`
- **Requests**: `GET /requests`, `GET /requests/new-info`, `POST /requests`, `GET /requests/{id}`, `POST /requests/{id}/claim|release|upload|confirm|reject|report`, `GET /requests/{id}/download`
- **Library**: `GET /library`, `GET /library/{id}/download`
- **Me**: `GET /me/dashboard`, `POST /me/signin`, `POST /me/profile`
- **Admin**: `GET /admin/overview`, `GET|POST /admin/settings`, `POST /admin/settings/reset`, `POST /admin/settings/test-email`, `POST /admin/gift`, `GET /admin/users`, `POST /admin/users/{id}/toggle-active`, `GET /admin/requests`, `POST /admin/requests/{id}/close`, `GET /admin/reports`, `POST /admin/reports/{id}/dismiss`

### Auth

- Signed cookie session (`litshare_session`, httponly, 30 days)
- CSRF: double-submit cookie (`litshare_csrf`, **non-httponly** for SPA), validated via `X-CSRF-Token` header
- API endpoints use `require_csrf_header` dependency

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

**Complete**: Vue 3 SPA migration done. All Sprints 0-3 finished.
- Jinja2 templates and old HTML routes fully removed
- All functionality available via JSON API + Vue frontend

## Business Rules

- Points system: publish deducts bounty, completion pays helper, timeout refunds
- Request status: open → claimed → awaiting_confirm → completed (also: expired, closed)
- PDF redaction: metadata cleared, email/IP blacked out on first/last pages
- Rate limits: max 3 active requests, same-journal monthly limit, report threshold
- Background scheduler (APScheduler): auto-expires overdue requests, auto-confirms overdue claims
