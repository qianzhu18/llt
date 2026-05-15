"""Timezone helpers. Storage is naive UTC; user-facing day boundaries are Asia/Shanghai."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


CN_TZ = ZoneInfo("Asia/Shanghai")


def now_utc_naive() -> datetime:
    """Naive UTC datetime — matches SQLAlchemy func.now() defaults across DBs."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today_cn_str() -> str:
    return datetime.now(CN_TZ).strftime("%Y-%m-%d")


def to_cn(dt: datetime) -> datetime:
    """Convert a naive-UTC stored datetime into Asia/Shanghai for display."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CN_TZ)


def humanize_remaining(deadline: datetime) -> str:
    """Friendly '剩 N 天 M 小时' string. Negative → '已过期'."""
    if deadline is None:
        return "-"
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    remaining = deadline - datetime.now(timezone.utc)
    secs = int(remaining.total_seconds())
    if secs <= 0:
        return "已过期"
    days, secs = divmod(secs, 86400)
    hours, _ = divmod(secs, 3600)
    if days >= 1:
        return f"剩 {days} 天 {hours} 时"
    if hours >= 1:
        return f"剩 {hours} 小时"
    return "剩 <1 小时"
