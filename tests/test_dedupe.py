"""Unit tests for the pure duplicate-detection function."""

from __future__ import annotations

import uuid
from datetime import date

from app.api_models import Receipt, ReceiptCreate
from app.dedupe import duplicate_of


def _stored(merchant, day, total, currency="INR"):
    return Receipt(
        id=str(uuid.uuid4()),
        owner_persona_id="m",
        paid_by_persona_id="m",
        merchant=merchant,
        purchase_date=day,
        currency=currency,
        total=total,
        base_currency="INR",
        base_amount=total,
    )


def _incoming(merchant, day, total, currency="INR", trip_id="t"):
    return ReceiptCreate(
        trip_id=trip_id, merchant=merchant, purchase_date=day, total=total, currency=currency
    )


EXISTING = [
    _stored("Bistro", date(2026, 6, 5), 100.0),
    _stored("BigBasket", date(2026, 6, 12), 200.0),
]


def test_exact_match_is_a_duplicate():
    dup = duplicate_of(_incoming("Bistro", date(2026, 6, 5), 100.0), EXISTING)
    assert dup is not None and dup.merchant == "Bistro"


def test_merchant_case_and_whitespace_insensitive():
    dup = duplicate_of(_incoming("  bISTRO ", date(2026, 6, 5), 100.0), EXISTING)
    assert dup is not None


def test_currency_case_insensitive_and_total_rounding():
    dup = duplicate_of(_incoming("Bistro", date(2026, 6, 5), 100.004, currency="inr"), EXISTING)
    assert dup is not None  # 100.004 rounds to 100.00; inr == INR


def test_different_total_is_not_a_duplicate():
    assert duplicate_of(_incoming("Bistro", date(2026, 6, 5), 101.0), EXISTING) is None


def test_different_date_is_not_a_duplicate():
    assert duplicate_of(_incoming("Bistro", date(2026, 6, 6), 100.0), EXISTING) is None


def test_different_merchant_is_not_a_duplicate():
    assert duplicate_of(_incoming("Cafe", date(2026, 6, 5), 100.0), EXISTING) is None


def test_different_currency_is_not_a_duplicate():
    assert duplicate_of(_incoming("Bistro", date(2026, 6, 5), 100.0, currency="USD"), EXISTING) is None


def test_missing_key_field_never_blocks():
    # A candidate lacking merchant/date/total/currency can't be judged -> not a dup.
    assert duplicate_of(_incoming(None, date(2026, 6, 5), 100.0), EXISTING) is None
    assert duplicate_of(_incoming("Bistro", None, 100.0), EXISTING) is None
    assert duplicate_of(_incoming("Bistro", date(2026, 6, 5), None), EXISTING) is None
    assert duplicate_of(_incoming("Bistro", date(2026, 6, 5), 100.0, currency=""), EXISTING) is None


def test_empty_existing_list():
    assert duplicate_of(_incoming("Bistro", date(2026, 6, 5), 100.0), []) is None
