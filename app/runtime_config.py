"""Runtime config — read-through from system_settings table with .env fallback.

Pattern: every business knob calls get_setting(db, "key", settings.KEY) so admins
can override at runtime via the system_settings table (M4 UI). The .env value
is the immutable default; no seeding happens, so removing a row reverts to .env.
"""
from typing import Any, Callable, TypeVar

from sqlalchemy.orm import Session

from .models import SystemSetting


T = TypeVar("T")


def get_setting(db: Session, key: str, default: T, cast: Callable[[str], T] = str) -> T:
    row = db.get(SystemSetting, key)
    if row is None:
        return default
    try:
        return cast(row.value)
    except (ValueError, TypeError):
        return default


def set_setting(db: Session, key: str, value: Any) -> None:
    """Upsert a setting. Caller is responsible for committing."""
    row = db.get(SystemSetting, key)
    if row is None:
        db.add(SystemSetting(key=key, value=str(value)))
    else:
        row.value = str(value)


def as_int(v: str) -> int:
    return int(v)


def as_bool(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on")
