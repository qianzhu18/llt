"""ORM models. Designed to work on SQLite/MySQL/PostgreSQL with no source changes."""
from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


# SQLite only treats *literal* INTEGER columns as ROWID aliases (autoincrement works).
# BIGINT columns don't, so inserts without explicit id fail with NOT NULL.
# This variant gives MySQL/PG their BIGINT while keeping SQLite happy.
BigInt = BigInteger().with_variant(Integer(), "sqlite")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class HelpRequest(Base):
    __tablename__ = "help_requests"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    requester_id: Mapped[int] = mapped_column(BigInt, ForeignKey("users.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[str] = mapped_column(String(500), nullable=False)
    journal: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    extra: Mapped[str] = mapped_column(Text, nullable=False, default="")
    bounty: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open", index=True)
    # status: open, claimed, awaiting_confirm, completed, closed, expired
    claimed_by: Mapped[int | None] = mapped_column(BigInt, ForeignKey("users.id"), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirm_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    request_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    library_paper_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("library_papers.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(BigInt, ForeignKey("help_requests.id"), index=True, nullable=False)
    helper_id: Mapped[int] = mapped_column(BigInt, ForeignKey("users.id"), nullable=False)
    original_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sanitized_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    desensitized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    size_bytes: Mapped[int] = mapped_column(BigInt, nullable=False, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class LibraryPaper(Base):
    """Completed paper repository — once a request finishes, the PDF is sealed here for others to download free."""
    __tablename__ = "library_papers"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[str] = mapped_column(String(500), nullable=False)
    journal: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class PointTransaction(Base):
    """Append-only points ledger. Strong consistency by avoiding mid-transaction mutations on users.points."""
    __tablename__ = "point_transactions"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("users.id"), index=True, nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    ref_request_id: Mapped[int | None] = mapped_column(BigInt, nullable=True)
    note: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)


class DailySignin(Base):
    __tablename__ = "daily_signins"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_signin_user_date"),)

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("users.id"), nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(BigInt, ForeignKey("help_requests.id"), index=True, nullable=False)
    reporter_id: Mapped[int] = mapped_column(BigInt, ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class SystemSetting(Base):
    """Admin-editable runtime config. Falls back to .env defaults on first boot."""
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
