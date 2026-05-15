"""Points ledger — atomic credit/debit that updates users.points and writes a
point_transactions row in the same transaction. Caller commits."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PointTransaction, User


# Canonical `reason` values used across the codebase. Grep these to find every
# place a particular flow touches points.
REASON_SIGNIN = "signin"
REASON_PUBLISH_DEDUCT = "publish_deduct"
REASON_PUBLISH_REFUND_TIMEOUT = "publish_refund_timeout"
REASON_PUBLISH_REFUND_CLOSED = "publish_refund_closed"
REASON_HELP_ACCEPTED = "help_accepted"
REASON_ADMIN_GIFT = "admin_gift"


class InsufficientPoints(Exception):
    """Raised when a debit would push balance below zero."""


def adjust_points(
    db: Session,
    user_id: int,
    delta: int,
    reason: str,
    ref_request_id: Optional[int] = None,
    note: str = "",
    *,
    allow_negative: bool = False,
) -> int:
    """Credit (delta > 0) or debit (delta < 0) the user and append a ledger row.

    Returns the new balance. Raises InsufficientPoints if a debit would go
    below zero (unless allow_negative=True for admin overrides).
    """
    if delta == 0:
        return db.get(User, user_id).points

    # Row-lock the user for the txn. SQLite no-ops; MySQL/PG serialize concurrent writers.
    user = db.execute(
        select(User).where(User.id == user_id).with_for_update()
    ).scalar_one()

    new_balance = user.points + delta
    if not allow_negative and new_balance < 0:
        raise InsufficientPoints(
            f"user_id={user_id} balance={user.points} delta={delta}"
        )

    user.points = new_balance
    db.add(PointTransaction(
        user_id=user_id,
        delta=delta,
        reason=reason,
        ref_request_id=ref_request_id,
        note=note,
    ))
    return new_balance
