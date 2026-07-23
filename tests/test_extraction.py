"""Extraction pipeline tests — these catch the failures we'll actually hit:
malformed model JSON, non-receipts, foreign currencies, partial receipts, and
rate-limit/timeout errors. They run offline via the `generate=` seam.
"""

from __future__ import annotations

import json

from app.extraction import extract_receipt
from app.schemas import Category
from tests.conftest import (
    CLEAN_RECEIPT,
    FOREIGN_CURRENCY_RECEIPT,
    NON_RECEIPT,
    PARTIAL_RECEIPT_NO_TOTAL,
    fixed_response,
    raising_generate,
    scripted_responses,
)

IMG = b"fake-bytes"
MIME = "image/jpeg"


def test_clean_receipt_parses_to_typed_fields():
    result = extract_receipt(IMG, MIME, generate=fixed_response(CLEAN_RECEIPT))

    assert result.used_fallback is False
    r = result.receipt
    assert r is not None and r.is_receipt
    assert r.merchant == "Whole Foods Market"
    assert r.total == 45.47
    assert r.category is Category.groceries
    assert str(r.purchase_date) == "2026-07-15"
    assert len(r.line_items) == 2


def test_foreign_currency_is_normalized_to_iso():
    result = extract_receipt(IMG, MIME, generate=fixed_response(FOREIGN_CURRENCY_RECEIPT))

    assert result.receipt.currency == "EUR"  # validator upper-cased it
    assert "tax" in result.receipt.low_confidence_fields


def test_non_receipt_is_a_valid_rejection_not_a_crash():
    result = extract_receipt(IMG, MIME, generate=fixed_response(NON_RECEIPT))

    assert result.used_fallback is False
    assert result.receipt.is_receipt is False
    assert result.receipt.rejection_reason
    assert result.receipt.total is None  # no garbage fields invented


def test_partial_receipt_keeps_total_null_and_flags_it():
    result = extract_receipt(IMG, MIME, generate=fixed_response(PARTIAL_RECEIPT_NO_TOTAL))

    r = result.receipt
    assert r.is_receipt
    assert r.total is None  # never guessed
    assert "total" in r.low_confidence_fields


def test_malformed_json_then_valid_recovers_on_retry():
    gen = scripted_responses("{ this is not json", CLEAN_RECEIPT)

    result = extract_receipt(IMG, MIME, generate=gen)

    assert result.used_fallback is False
    assert result.receipt.merchant == "Whole Foods Market"


def test_persistently_malformed_json_falls_back_gracefully():
    gen = fixed_response("{ still broken")

    result = extract_receipt(IMG, MIME, generate=gen)

    assert result.receipt is None
    assert result.used_fallback is True
    assert result.error and "validation_error" in result.error
    assert result.raw == "{ still broken"  # raw kept for audit


def test_blank_date_string_coerces_to_none():
    payload = {**CLEAN_RECEIPT, "purchase_date": "unknown"}
    result = extract_receipt(IMG, MIME, generate=fixed_response(payload))

    assert result.receipt.purchase_date is None


def test_generation_error_is_caught_and_reported():
    gen = raising_generate(RuntimeError("connection reset by peer"))

    result = extract_receipt(IMG, MIME, generate=gen)

    assert result.receipt is None
    assert result.used_fallback is True
    assert "generation_error" in result.error


def test_quota_error_is_classified_as_rate_limited():
    # A 429 / quota exception gets a distinct, user-actionable classification
    # (drives the friendly "daily limit reached" message in the UI).
    gen = raising_generate(RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded"))

    result = extract_receipt(IMG, MIME, generate=gen)

    assert result.used_fallback is True
    assert result.error == "rate_limited"


def test_schema_rejects_bad_category_and_falls_back():
    payload = {**CLEAN_RECEIPT, "category": "not-a-real-category"}
    result = extract_receipt(IMG, MIME, generate=fixed_response(payload))

    # Enum validation fails -> bounded retry -> fallback (same bad payload).
    assert result.used_fallback is True
    assert "validation_error" in result.error
    # sanity: the payload really was otherwise valid JSON
    assert json.loads(result.raw)["merchant"] == "Whole Foods Market"
