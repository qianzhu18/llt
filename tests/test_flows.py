from __future__ import annotations

from pathlib import Path

import fitz
from sqlalchemy import func, select

import app.main as main_mod
import app.routers.admin as admin_mod
from app.models import Attachment, DailySignin, HelpRequest, LibraryPaper, PointTransaction, SystemSetting, User
from app.points import REASON_PUBLISH_DEDUCT, REASON_SIGNIN
from app.security import CSRF_COOKIE, SESSION_COOKIE, hash_password, make_verify_token
from app.settings import settings


PASSWORD = "password123"


def csrf_token(client) -> str:
    return client.cookies.get(CSRF_COOKIE) or ""


def post_form(client, url: str, data: dict | None = None, *, files=None, follow_redirects: bool = True):
    payload = {"_csrf": csrf_token(client)}
    if data:
        payload.update(data)
    return client.post(url, data=payload, files=files, follow_redirects=follow_redirects)


def login(client, email: str, password: str = PASSWORD):
    client.get("/auth/login")
    return post_form(
        client,
        "/auth/login",
        {"email": email, "password": password},
        follow_redirects=False,
    )


def logout(client):
    client.get("/")
    return post_form(client, "/auth/logout", follow_redirects=False)


def make_user(SessionLocal, email: str, *, nickname: str = "User", points: int = 0, verified: bool = True, is_admin: bool = False) -> int:
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


def test_register_verify_login_and_csrf(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]
    email = "alice@example.com"

    client.get("/auth/register")
    response = client.post(
        "/auth/register",
        data={"email": email, "nickname": "Alice", "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf_invalid"

    response = post_form(
        client,
        "/auth/register",
        {"email": email, "nickname": "Alice", "password": PASSWORD},
    )
    assert response.status_code == 200
    assert "注册成功，请验证邮箱" in response.text

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        assert user.email_verified is False

    response = login(client, email)
    assert response.status_code == 403
    assert "邮箱尚未验证" in response.text

    client.get("/auth/login")
    response = post_form(client, "/auth/resend-verify", {"email": email})
    assert response.status_code == 200
    assert "验证邮件已处理" in response.text

    response = client.get(f"/auth/verify?token={make_verify_token(email)}")
    assert response.status_code == 200
    assert "邮箱已验证" in response.text

    response = login(client, email)
    assert response.status_code == 303
    assert client.cookies.get(SESSION_COOKIE)


def test_signin_is_idempotent(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]
    email = "signin@example.com"
    make_user(SessionLocal, email, nickname="Signer", points=0)

    response = login(client, email)
    assert response.status_code == 303

    post_form(client, "/me/signin", follow_redirects=False)
    post_form(client, "/me/signin", follow_redirects=False)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        signins = db.scalar(select(func.count(DailySignin.id)).where(DailySignin.user_id == user.id))
        tx_count = db.scalar(
            select(func.count(PointTransaction.id)).where(
                PointTransaction.user_id == user.id,
                PointTransaction.reason == REASON_SIGNIN,
            )
        )
        assert signins == 1
        assert tx_count == 1
        assert user.points == settings.SIGNIN_POINTS


def test_request_lifecycle_claim_upload_confirm_and_library_sink(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]

    make_user(SessionLocal, "requester@example.com", nickname="Requester", points=50)
    make_user(SessionLocal, "helper@example.com", nickname="Helper", points=0)

    assert login(client, "requester@example.com").status_code == 303
    client.get("/requests/new")
    response = post_form(
        client,
        "/requests/new",
        {
            "title": "A Useful Paper",
            "authors": "Alice, Bob",
            "journal": "Nature",
            "year": "2024",
            "extra": "Need the full PDF",
            "bounty": "20",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    with SessionLocal() as db:
        req = db.scalar(select(HelpRequest).where(HelpRequest.title == "A Useful Paper"))
        requester = db.scalar(select(User).where(User.email == "requester@example.com"))
        assert req is not None
        req_id = req.id
        assert req.status == "open"
        assert requester.points == 30
        assert db.scalar(
            select(func.count(PointTransaction.id)).where(
                PointTransaction.user_id == requester.id,
                PointTransaction.reason == REASON_PUBLISH_DEDUCT,
                PointTransaction.ref_request_id == req_id,
            )
        ) == 1

    logout(client)
    assert login(client, "helper@example.com").status_code == 303

    response = post_form(client, f"/requests/{req_id}/claim", follow_redirects=False)
    assert response.status_code == 303

    response = post_form(
        client,
        f"/requests/{req_id}/upload",
        files={"pdf": ("paper.pdf", sample_pdf_bytes(), "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 303

    with SessionLocal() as db:
        req = db.get(HelpRequest, req_id)
        helper = db.scalar(select(User).where(User.email == "helper@example.com"))
        attachment = db.scalar(select(Attachment).where(Attachment.request_id == req_id))
        assert req.status == "awaiting_confirm"
        assert req.claimed_by == helper.id
        assert attachment is not None
        assert Path(attachment.original_path).exists()

    logout(client)
    assert login(client, "requester@example.com").status_code == 303
    response = post_form(client, f"/requests/{req_id}/confirm", follow_redirects=False)
    assert response.status_code == 303

    with SessionLocal() as db:
        req = db.get(HelpRequest, req_id)
        helper = db.scalar(select(User).where(User.email == "helper@example.com"))
        paper = db.get(LibraryPaper, req.library_paper_id)
        assert req.status == "completed"
        assert helper.points == 20
        assert paper is not None
        assert Path(paper.file_path).exists()
        assert Path(paper.file_path).with_name(f"{Path(paper.file_path).stem}.sanitized.pdf").exists()

    download = client.get(f"/requests/{req_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/pdf")

    with SessionLocal() as db:
        paper = db.get(LibraryPaper, req.library_paper_id)
        assert paper.download_count == 1

    logout(client)
    library_page = client.get("/library?q=Useful")
    assert library_page.status_code == 200
    assert "A Useful Paper" in library_page.text
    assert "登录后下载" in library_page.text

    assert login(client, "requester@example.com").status_code == 303
    library_download = client.get(f"/library/{req.library_paper_id}/download")
    assert library_download.status_code == 200
    assert library_download.headers["content-type"].startswith("application/pdf")

    with SessionLocal() as db:
        paper = db.get(LibraryPaper, req.library_paper_id)
        assert paper.download_count == 2


def test_admin_gift_and_force_close_refunds_bounty(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]

    make_user(SessionLocal, "admin@example.com", nickname="Admin", points=0, is_admin=True)
    make_user(SessionLocal, "borrower@example.com", nickname="Borrower", points=0)

    assert login(client, "admin@example.com").status_code == 303
    response = post_form(
        client,
        "/admin/gift",
        {"target": "borrower@example.com", "delta": "40", "note": "bootstrap"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    with SessionLocal() as db:
        borrower = db.scalar(select(User).where(User.email == "borrower@example.com"))
        assert borrower.points == 40

    logout(client)
    assert login(client, "borrower@example.com").status_code == 303
    client.get("/requests/new")
    response = post_form(
        client,
        "/requests/new",
        {
            "title": "Need Closing",
            "authors": "Carol",
            "journal": "Science",
            "year": "2023",
            "extra": "",
            "bounty": "30",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    with SessionLocal() as db:
        req = db.scalar(select(HelpRequest).where(HelpRequest.title == "Need Closing"))
        req_id = req.id

    logout(client)
    assert login(client, "admin@example.com").status_code == 303
    response = post_form(
        client,
        f"/admin/requests/{req_id}/close",
        {"note": "cleanup"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    with SessionLocal() as db:
        borrower = db.scalar(select(User).where(User.email == "borrower@example.com"))
        req = db.get(HelpRequest, req_id)
        assert req.status == "closed"
        assert borrower.points == 40


def test_publish_limit_blocks_too_many_active_requests(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]

    make_user(SessionLocal, "limited@example.com", nickname="Limited", points=100)
    with SessionLocal() as db:
        db.add(SystemSetting(key="MAX_ACTIVE_REQUESTS", value="1"))
        db.commit()

    assert login(client, "limited@example.com").status_code == 303
    response = client.get("/requests/new")
    assert response.status_code == 200
    assert "进行中 0/1" in response.text

    response = post_form(
        client,
        "/requests/new",
        {
            "title": "First Active Request",
            "authors": "Alice",
            "journal": "Cell",
            "year": "2024",
            "extra": "",
            "bounty": "10",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    response = client.get("/requests/new")
    assert response.status_code == 200
    assert "进行中 1/1" in response.text
    assert "同时进行中的求助上限" in response.text

    response = post_form(
        client,
        "/requests/new",
        {
            "title": "Second Active Request",
            "authors": "Bob",
            "journal": "Nature",
            "year": "2024",
            "extra": "",
            "bounty": "10",
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert "已达到上限 1 条" in response.text


def test_runtime_site_copy_is_used_in_templates(app_env):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]

    with SessionLocal() as db:
        db.add(SystemSetting(key="SITE_TITLE", value="文献互助测试站"))
        db.add(SystemSetting(key="SITE_SLOGAN", value="运行时配置立即生效"))
        db.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert "文献互助测试站" in response.text
    assert "运行时配置立即生效" in response.text

    response = client.get("/auth/login")
    assert response.status_code == 200
    assert "<title>登录 · 文献互助测试站</title>" in response.text


def test_admin_settings_can_send_smtp_test_email(app_env, monkeypatch):
    client = app_env["client"]
    SessionLocal = app_env["SessionLocal"]
    make_user(SessionLocal, "admin@example.com", nickname="Admin", points=0, is_admin=True)

    sent = {}

    def fake_send_email(db, *, to: str, subject: str, body: str):
        sent["to"] = to
        sent["subject"] = subject
        sent["body"] = body
        return {"mode": "smtp", "detail": "ok"}

    monkeypatch.setattr(admin_mod, "send_email", fake_send_email)

    with SessionLocal() as db:
        db.add(SystemSetting(key="SMTP_HOST", value="smtp.qq.com"))
        db.add(SystemSetting(key="SMTP_PORT", value="587"))
        db.add(SystemSetting(key="SMTP_USER", value="bot@qq.com"))
        db.add(SystemSetting(key="SMTP_PASS", value="secret"))
        db.add(SystemSetting(key="SMTP_FROM", value="bot@qq.com"))
        db.add(SystemSetting(key="SMTP_USE_SSL", value="false"))
        db.commit()

    assert login(client, "admin@example.com").status_code == 303
    response = client.get("/admin/settings")
    assert response.status_code == 200
    assert "SMTP 当前状态" in response.text
    assert "smtp.qq.com:587" in response.text

    response = post_form(
        client,
        "/admin/settings/test-email",
        {"test_email": "deliver@example.com"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "测试邮件已发送到 deliver@example.com" in response.text
    assert sent["to"] == "deliver@example.com"
    assert "SMTP 测试邮件" in sent["subject"]


def test_health_reports_deploy_metadata(app_env, monkeypatch, tmp_path):
    branch_file = tmp_path / ".deploy_branch"
    rev_file = tmp_path / ".deploy_rev"
    branch_file.write_text("codex/m6-runtime-hardening", encoding="utf-8")
    rev_file.write_text("2573de73c2bda31ca0b08495f428dcb4d7df7002", encoding="utf-8")

    monkeypatch.setattr(main_mod, "DEPLOY_BRANCH_FILE", branch_file)
    monkeypatch.setattr(main_mod, "DEPLOY_REV_FILE", rev_file)

    response = app_env["client"].get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "2573de7",
        "deploy_branch": "codex/m6-runtime-hardening",
        "deploy_rev": "2573de73c2bda31ca0b08495f428dcb4d7df7002",
    }
