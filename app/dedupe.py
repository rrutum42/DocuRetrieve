"""Duplicate-receipt detection (pure, deterministic).

Uploading the *same* receipt twice into a trip is an easy mistake — two people
photograph the shared dinner bill, or someone taps save twice. That silently
double-counts a trip's spend and every settle-up balance derived from it.

We reject an upload that exactly matches one already in the trip on the fields
that identify a specific transaction: merchant, purchase date, total, and
currency. The match is deliberately *strict* (all four, exact) so a genuinely
separate purchase — a different amount, a different day, a different shop — is
never blocked. A true repeat purchase (same shop, same day, same price) can
still be saved intentionally via the `allow_duplicate` override, so the human
stays in control (the model proposes, a human confirms).

Kept a pure function so it's trivially testable and has no repository/DB
dependency: the caller passes the candidate and the trip's existing receipts.
"""

from __future__ import annotations

from typing import Protocol

from datetime import date


class _HasReceiptKey(Protocol):
    """The subset of fields that identify a transaction. Both ReceiptCreate
    (the incoming save) and Receipt (a stored row) satisfy this."""

    merchant: str | None
    purchase_date: date | None
    currency: str | None
    total: float | None


def _norm_merchant(m: str | None) -> str | None:
    if m is None:
        return None
    n = m.strip().casefold()
    return n or None


def _key(r: _HasReceiptKey) -> tuple | None:
    """The identity tuple for a receipt, or None if it lacks the fields needed
    to judge a duplicate confidently. We require all four so we never block on a
    weak, partial match (e.g. two amount-only receipts on the same day)."""
    merchant = _norm_merchant(r.merchant)
    if (
        merchant is None
        or r.purchase_date is None
        or r.total is None
        or not r.currency
    ):
        return None
    # Round the total so 100.0 and 100.00 (or tiny float noise) compare equal.
    return (merchant, r.purchase_date, round(r.total, 2), r.currency.strip().upper())


def duplicate_of(
    candidate: _HasReceiptKey, existing: list[_HasReceiptKey]
) -> _HasReceiptKey | None:
    """Return the first receipt in `existing` that is an exact duplicate of
    `candidate`, or None. `existing` should already be scoped to one trip."""
    key = _key(candidate)
    if key is None:
        return None  # not enough to judge -> never block
    for r in existing:
        if _key(r) == key:
            return r
    return None
