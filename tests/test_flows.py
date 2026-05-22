from __future__ import annotations

from pathlib import Path

import fitz
from sqlalchemy import func, select

import app.main as main_mod
import app.routers.api.admin as api_admin_mod
from app.models import Attachment, DailySignin, HelpRequest, LibraryPaper, PointTransaction, Report, SystemSetting, User
from app.points import REASON_PUBLISH_DEDUCT, REASON_SIGNIN
from app.security import CSRF_COOKIE, SESSION_COOKIE, hash_password, make_verify_token
from app.settings import settings


PASSWORD = "password123"
API = "/api/v1"


def csrf(client) -> str:
    return client.cookies.get(CSRF_COOKIE) or ""


def api(client, method: str, path: str, json=None, *, with_csrf=True, **kw):
    headers = {}
    if with_csrf:
        headers["X-CSRF-Token"] = csrf(client)
    return client.request(method, f"{API}{path}", json=json, headers=headers, **kw)


def api_get(client, path: str, params=None):
    return client.get(f"{API}{path}", params=params)


def api_post(client, path: str, json=None):
    return api(client, "POST", path, json)


def login_user(client, email: str, password: str = PASSWORD):
    return api_post(client, "/auth/login", {"email": email, "password": password})


def make_user(SessionLocal, email: str, *, nickname="User", points=0, verified=True, is_admin=False) -> int:
    with SessionLocal() as db:
        user = User(
            email=email,
            password_hash=hash_password(PASSWORD),
            nickname=nickname,
            points=points,
            is_admin=is_admin,
            is_active=True,
            email_verified=verified,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def verify_email(email: str):
    """Mark email as verified directly in the DB via the test's SessionLocal."""
    pass  # handled inline in tests


def sample_pdf_bytes() -> bytes:
    doc = fitz.open()
    blob = ("公益文献互助 PDF 测试样本 " * 300).strip()
    for _ in range(2):
        page = doc.new_page()
        page.insert_textbox((36, 36, 540, 760), blob, fontsize=12)
    data = doc.tobytes(garbage=4, deflate=False)
    doc.close()
    if len(data) <= 1024:
        data += b"\n%pad\n" + (b"x" * 2048)
    assert len(data) > 1024
    return data


# ──────────────────────────────────────────────
# Test 1: Register, login, me, logout
# ──────────────────────────────────────────────
def test_register_login_logout_me(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]
    email = "alice@test.com"

    # Register
    r = api_post(client, "/auth/register", {"email": email, "nickname": "Alice", "password": PASSWORD})
    assert r.status_code == 200
    assert r.json()["user"]["email"] == email

    # Login fails before verification
    r = login_user(client, email)
    assert r.status_code == 403

    # Verify email in DB
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        user.email_verified = True
        db.commit()

    # Login succeeds
    r = login_user(client, email)
    assert r.status_code == 200
    assert r.json()["user"]["email"] == email
    assert client.cookies.get(SESSION_COOKIE)

    # GET /auth/me
    r = api_get(client, "/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == email
    assert r.json()["nickname"] == "Alice"

    # Logout
    r = api_post(client, "/auth/logout")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Me after logout → 401
    r = api_get(client, "/auth/me")
    assert r.status_code == 401


# ──────────────────────────────────────────────
# Test 2: Signin awards points (idempotent)
# ──────────────────────────────────────────────
def test_signin_is_idempotent(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]
    email = "signer@test.com"
    make_user(SessionLocal, email, nickname="Signer", points=0)

    assert login_user(client, email).status_code == 200

    # First signin
    r = api_post(client, "/me/signin")
    assert r.status_code == 200
    assert r.json()["points_awarded"] > 0

    # Second signin same day → 400
    r = api_post(client, "/me/signin")
    assert r.status_code == 400
    assert "已经签到" in r.json()["detail"]

    # Dashboard shows correct state
    r = api_get(client, "/me")
    assert r.status_code == 200
    assert r.json()["signed_today"] is True
    assert r.json()["points"] == settings.SIGNIN_POINTS


# ──────────────────────────────────────────────
# Test 3: Full request lifecycle
# ──────────────────────────────────────────────
def test_request_lifecycle_claim_upload_confirm(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]
    make_user(SessionLocal, "req@test.com", nickname="Requester", points=50)
    make_user(SessionLocal, "help@test.com", nickname="Helper", points=0)

    # Requester creates request
    assert login_user(client, "req@test.com").status_code == 200
    r = api_post(client, "/requests", {
        "title": "A Useful Paper", "authors": "Alice, Bob",
        "journal": "Nature", "year": 2024, "extra": "Need PDF", "bounty": 20,
    })
    assert r.status_code == 200
    req_id = r.json()["id"]
    assert r.json()["status"] == "open"

    with SessionLocal() as db:
        req = db.get(HelpRequest, req_id)
        assert req.status == "open"
        requester = db.scalar(select(User).where(User.email == "req@test.com"))
        assert requester.points == 30  # 50 - 20

    # Helper claims
    assert login_user(client, "help@test.com").status_code == 200
    r = api_post(client, f"/requests/{req_id}/claim")
    assert r.status_code == 200
    assert r.json()["status"] == "claimed"

    # Helper uploads PDF
    pdf = sample_pdf_bytes()
    r = client.post(
        f"{API}/requests/{req_id}/upload",
        files={"pdf": ("paper.pdf", pdf, "application/pdf")},
        headers={"X-CSRF-Token": csrf(client)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "awaiting_confirm"

    with SessionLocal() as db:
        req = db.get(HelpRequest, req_id)
        assert req.status == "awaiting_confirm"
        att = db.scalar(select(Attachment).where(Attachment.request_id == req_id))
        assert att is not None
        assert Path(att.original_path).exists()

    # Requester confirms
    assert login_user(client, "req@test.com").status_code == 200
    r = api_post(client, f"/requests/{req_id}/confirm")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"

    with SessionLocal() as db:
        req = db.get(HelpRequest, req_id)
        helper = db.scalar(select(User).where(User.email == "help@test.com"))
        paper = db.get(LibraryPaper, req.library_paper_id)
        assert req.status == "completed"
        assert helper.points == 20
        assert paper is not None
        assert Path(paper.file_path).exists()


# ──────────────────────────────────────────────
# Test 4: Reject and reclaim
# ──────────────────────────────────────────────
def test_reject_and_reclaim(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]
    make_user(SessionLocal, "req2@test.com", points=50)
    make_user(SessionLocal, "help2@test.com", points=0)

    assert login_user(client, "req2@test.com").status_code == 200
    r = api_post(client, "/requests", {
        "title": "Reject Test", "authors": "X", "year": 2024, "bounty": 10,
    })
    req_id = r.json()["id"]

    assert login_user(client, "help2@test.com").status_code == 200
    api_post(client, f"/requests/{req_id}/claim")

    # Upload
    pdf = sample_pdf_bytes()
    client.post(
        f"{API}/requests/{req_id}/upload",
        files={"pdf": ("bad.pdf", pdf, "application/pdf")},
        headers={"X-CSRF-Token": csrf(client)},
    )

    # Requester rejects
    assert login_user(client, "req2@test.com").status_code == 200
    r = api_post(client, f"/requests/{req_id}/reject", {"reason": "wrong paper"})
    assert r.status_code == 200
    assert r.json()["status"] == "open"

    # Helper reclaims and re-uploads
    assert login_user(client, "help2@test.com").status_code == 200
    api_post(client, f"/requests/{req_id}/claim")
    client.post(
        f"{API}/requests/{req_id}/upload",
        files={"pdf": ("good.pdf", pdf, "application/pdf")},
        headers={"X-CSRF-Token": csrf(client)},
    )

    # Requester confirms
    assert login_user(client, "req2@test.com").status_code == 200
    r = api_post(client, f"/requests/{req_id}/confirm")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


# ──────────────────────────────────────────────
# Test 5: Admin gift and force close
# ──────────────────────────────────────────────
def test_admin_gift_and_force_close(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]
    make_user(SessionLocal, "admin@test.com", is_admin=True)
    make_user(SessionLocal, "borrower@test.com", points=0)

    # Admin gifts points
    assert login_user(client, "admin@test.com").status_code == 200
    r = api_post(client, "/admin/gift", {"target": "borrower@test.com", "delta": 40, "note": "bootstrap"})
    assert r.status_code == 200

    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.email == "borrower@test.com")).points == 40

    # Borrower creates request
    assert login_user(client, "borrower@test.com").status_code == 200
    r = api_post(client, "/requests", {
        "title": "Need Closing", "authors": "C", "year": 2023, "bounty": 30,
    })
    req_id = r.json()["id"]

    # Admin force-closes
    assert login_user(client, "admin@test.com").status_code == 200
    r = api_post(client, f"/admin/requests/{req_id}/close", {"note": "cleanup"})
    assert r.status_code == 200

    with SessionLocal() as db:
        req = db.get(HelpRequest, req_id)
        borrower = db.scalar(select(User).where(User.email == "borrower@test.com"))
        assert req.status == "closed"
        assert borrower.points == 40  # refunded


# ──────────────────────────────────────────────
# Test 6: Admin settings
# ──────────────────────────────────────────────
def test_admin_settings(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]
    make_user(SessionLocal, "admin2@test.com", is_admin=True)
    assert login_user(client, "admin2@test.com").status_code == 200

    # Get settings
    r = api_get(client, "/admin/settings")
    assert r.status_code == 200
    assert "items" in r.json()
    assert len(r.json()["items"]) > 0

    # Save a setting
    r = api_post(client, "/admin/settings", {"values": {"SITE_TITLE": "测试站"}, "toggles": []})
    assert r.status_code == 200
    assert r.json()["changed"] >= 0

    # Reset
    r = api_post(client, "/admin/settings/reset", {"key": "SITE_TITLE"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ──────────────────────────────────────────────
# Test 7: Library search and download
# ──────────────────────────────────────────────
def test_library_search_and_download(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]
    make_user(SessionLocal, "libreq@test.com", points=50)
    make_user(SessionLocal, "libhelp@test.com", points=0)

    # Create and complete a request
    assert login_user(client, "libreq@test.com").status_code == 200
    r = api_post(client, "/requests", {
        "title": "Library Paper", "authors": "Foo", "year": 2024, "bounty": 10,
    })
    req_id = r.json()["id"]

    assert login_user(client, "libhelp@test.com").status_code == 200
    api_post(client, f"/requests/{req_id}/claim")
    pdf = sample_pdf_bytes()
    client.post(
        f"{API}/requests/{req_id}/upload",
        files={"pdf": ("lib.pdf", pdf, "application/pdf")},
        headers={"X-CSRF-Token": csrf(client)},
    )

    assert login_user(client, "libreq@test.com").status_code == 200
    api_post(client, f"/requests/{req_id}/confirm")

    with SessionLocal() as db:
        paper_id = db.get(HelpRequest, req_id).library_paper_id

    # Search library
    r = api_get(client, "/library", {"q": "Library Paper"})
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    assert any(item["title"] == "Library Paper" for item in r.json()["items"])

    # Download
    r = client.get(f"{API}/library/{paper_id}/download")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")


# ──────────────────────────────────────────────
# Test 8: Home and search
# ──────────────────────────────────────────────
def test_home_and_search(app_env):
    client = app_env["client"]

    r = api_get(client, "/home")
    assert r.status_code == 200
    data = r.json()
    assert "activities" in data
    assert "recent_library" in data
    assert "library_count" in data
    assert "site_title" in data

    r = api_get(client, "/search", {"q": "test"})
    assert r.status_code == 200
    assert "library_results" in r.json()
    assert "open_req_results" in r.json()


# ──────────────────────────────────────────────
# Test 9: CSRF required
# ──────────────────────────────────────────────
def test_csrf_rejection(app_env):
    client = app_env["client"]

    # POST without CSRF token → 403
    r = client.post(f"{API}/auth/register", json={"email": "x@x.com", "nickname": "X", "password": PASSWORD})
    assert r.status_code == 403
    assert r.json()["detail"] == "csrf_invalid"


# ──────────────────────────────────────────────
# Test 10: Admin users and reports
# ──────────────────────────────────────────────
def test_admin_users_and_reports(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]
    admin_id = make_user(SessionLocal, "admin3@test.com", is_admin=True)
    user_id = make_user(SessionLocal, "user3@test.com", points=10)

    assert login_user(client, "admin3@test.com").status_code == 200

    # List users
    r = api_get(client, "/admin/users")
    assert r.status_code == 200
    assert r.json()["total"] >= 2

    # Toggle active
    r = api_post(client, f"/admin/users/{user_id}/toggle-active")
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # Re-enable
    r = api_post(client, f"/admin/users/{user_id}/toggle-active")
    assert r.status_code == 200
    assert r.json()["is_active"] is True

    # Can't disable self
    r = api_post(client, f"/admin/users/{admin_id}/toggle-active")
    assert r.status_code == 400

    # List reports (empty)
    r = api_get(client, "/admin/reports")
    assert r.status_code == 200
    assert r.json()["total"] == 0

    # Admin overview
    r = api_get(client, "/admin")
    assert r.status_code == 200
    assert "users" in r.json()
    assert "total_requests" in r.json()
