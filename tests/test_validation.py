"""Validation-layer tests: does our independent checker catch the model's
mistakes, and does safe self-correction only fill blanks (never overwrite)?"""

from __future__ import annotations

from datetime import date

from app.schemas import ExtractedReceipt
from app.validation import apply_report, validate_receipt

TODAY = date(2026, 7, 23)


def receipt(**kw) -> ExtractedReceipt:
    base = dict(is_receipt=True, currency="INR", total=100.0)
    base.update(kw)
    return ExtractedReceipt(**base)


# --- arithmetic consistency -------------------------------------------------

def test_consistent_totals_produce_no_warning():
    r = receipt(subtotal=90.0, tax=10.0, total=100.0)
    report = validate_receipt(r, today=TODAY)
    assert report.ok
    assert not any(i.field == "total" for i in report.issues)


def test_inconsistent_totals_are_flagged():
    # 90 + 10 = 100, but total reads 110 -> caught
    r = receipt(subtotal=90.0, tax=10.0, total=110.0)
    report = validate_receipt(r, today=TODAY)
    issues = [i for i in report.issues if i.field == "total"]
    assert issues and issues[0].severity == "warning"
    assert "add up" in issues[0].message


def test_rounding_within_tolerance_is_ok():
    r = receipt(subtotal=33.33, tax=6.67, total=40.0)  # exact
    assert validate_receipt(r, today=TODAY).ok
    r2 = receipt(subtotal=33.34, tax=6.67, total=40.0)  # 0.01 off -> tolerated
    assert not any(i.field == "total" for i in validate_receipt(r2, today=TODAY).issues)


def test_tip_included_in_consistency():
    r = receipt(subtotal=80.0, tax=8.0, tip=12.0, total=100.0)
    assert validate_receipt(r, today=TODAY).ok


# --- safe self-correction (fill blanks only) --------------------------------

def test_derives_missing_total_from_parts():
    r = receipt(subtotal=90.0, tax=10.0, total=None)
    report = validate_receipt(r, today=TODAY)
    assert report.derived.get("total") == 100.0


def test_derives_missing_subtotal_from_total():
    r = receipt(subtotal=None, tax=10.0, total=100.0)
    report = validate_receipt(r, today=TODAY)
    assert report.derived.get("subtotal") == 90.0


def test_derives_missing_tax():
    r = receipt(subtotal=90.0, tax=None, total=100.0)
    report = validate_receipt(r, today=TODAY)
    assert report.derived.get("tax") == 10.0


def test_does_not_overwrite_a_value_the_model_read():
    # All three present but inconsistent -> we FLAG, we do NOT change anything.
    r = receipt(subtotal=90.0, tax=10.0, total=105.0)
    report = validate_receipt(r, today=TODAY)
    assert report.derived == {}
    assert any(i.field == "total" for i in report.issues)


def test_negative_derivation_is_rejected():
    # total < tax would derive a negative subtotal -> refuse
    r = receipt(subtotal=None, tax=150.0, total=100.0)
    report = validate_receipt(r, today=TODAY)
    assert "subtotal" not in report.derived


# --- field sanity -----------------------------------------------------------

def test_future_date_flagged():
    r = receipt(subtotal=90.0, tax=10.0, purchase_date=date(2027, 1, 1))
    report = validate_receipt(r, today=TODAY)
    assert any(i.field == "purchase_date" for i in report.issues)


def test_unknown_currency_flagged():
    r = receipt(currency="XYZ", subtotal=90.0, tax=10.0)
    report = validate_receipt(r, today=TODAY)
    assert any(i.field == "currency" for i in report.issues)


def test_known_currency_ok():
    r = receipt(currency="EUR", subtotal=90.0, tax=10.0)
    assert not any(i.field == "currency" for i in validate_receipt(r, today=TODAY).issues)


def test_missing_total_is_a_hard_error():
    r = receipt(subtotal=None, tax=None, total=None)
    report = validate_receipt(r, today=TODAY)
    assert not report.ok  # error severity present
    assert any(i.severity == "error" and i.field == "total" for i in report.issues)


def test_line_items_mismatch_is_info_only():
    r = receipt(subtotal=100.0, tax=0.0, total=100.0, line_items=[{"description": "x", "amount": 40.0}])
    report = validate_receipt(r, today=TODAY)
    li = [i for i in report.issues if i.field == "line_items"]
    assert li and li[0].severity == "info"  # soft signal, not blocking


def test_non_receipt_is_not_validated():
    r = ExtractedReceipt(is_receipt=False, rejection_reason="a cat")
    assert validate_receipt(r, today=TODAY).issues == []


# --- apply_report merges flags + fills derived ------------------------------

def test_apply_report_fills_and_flags():
    r = receipt(subtotal=None, tax=10.0, total=100.0, purchase_date=date(2027, 1, 1))
    report = validate_receipt(r, today=TODAY)
    fixed = apply_report(r, report)
    assert fixed.subtotal == 90.0                       # derived filled in
    assert "purchase_date" in fixed.low_confidence_fields  # flag merged for review
