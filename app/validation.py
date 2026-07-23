"""Extraction validation & safe self-correction.

The model proposes; we verify. An LLM can misread a digit and hand back numbers
that don't add up, a date in the future, or a currency that isn't real — and its
own `low_confidence_fields` won't always catch that. This module checks the
model's arithmetic and field sanity independently, then:

  * derives fields the model left BLANK from ones it did read (safe algebra —
    e.g. subtotal = total - tax), and
  * FLAGS genuine inconsistencies for the human review step (we never silently
    overwrite a value the model actually read — that would defeat the point).

Pure and deterministic, so it's fully unit-tested and adds no cost per receipt.
"""

from __future__ import annotations

from datetime import date

from .schemas import ExtractedReceipt, ValidationIssue, ValidationReport

# A pragmatic ISO 4217 set — the currencies a traveling family realistically
# hits. Unknown codes get flagged, not rejected.
KNOWN_CURRENCIES = {
    "USD", "EUR", "GBP", "INR", "JPY", "AUD", "CAD", "CHF", "CNY", "SGD",
    "HKD", "THB", "NZD", "ZAR", "AED", "SEK", "NOK", "DKK", "MXN", "BRL",
    "KRW", "MYR", "IDR", "PHP", "VND", "TRY", "PLN", "CZK", "HUF", "ILS",
    "SAR", "QAR", "EGP", "LKR", "NPR", "PKR", "BDT",
}


def _tol(expected: float) -> float:
    """Money tolerance: absorb per-line rounding without waving through real
    errors. A flat floor plus a small relative component."""
    return max(0.05, abs(expected) * 0.005)


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= _tol(b)


def validate_receipt(
    r: ExtractedReceipt, today: date | None = None
) -> ValidationReport:
    """Independently check a parsed receipt. `today` is injectable for tests."""
    today = today or date.today()
    issues: list[ValidationIssue] = []
    derived: dict[str, float] = {}

    # Non-receipts and rejections have nothing to validate.
    if not r.is_receipt:
        return ValidationReport(issues=issues, derived=derived)

    sub, tax, tip, total = r.subtotal, r.tax, r.tip, r.total

    # --- Safe self-correction: fill BLANK fields from present ones ----------
    # Only when it's unambiguous. We never change a value the model actually read.
    tax0 = tax or 0.0
    tip0 = tip or 0.0
    if total is None and sub is not None:
        total = round(sub + tax0 + tip0, 2)
        derived["total"] = total
    elif sub is None and total is not None:
        sub = round(total - tax0 - tip0, 2)
        if sub >= 0:
            derived["subtotal"] = sub
        else:
            sub = None  # would be negative -> not a safe derivation
    elif tax is None and sub is not None and total is not None:
        maybe = round(total - sub - tip0, 2)
        if maybe >= 0 and maybe <= total:
            tax = maybe
            derived["tax"] = tax

    # --- Arithmetic consistency (only when we have the pieces) --------------
    if sub is not None and total is not None:
        expected = round(sub + (tax or 0.0) + (tip or 0.0), 2)
        if not _close(expected, total):
            issues.append(
                ValidationIssue(
                    field="total",
                    severity="warning",
                    message=(
                        f"Numbers don't add up: subtotal + tax + tip = "
                        f"{expected:.2f}, but total reads {total:.2f}. "
                        f"Please check."
                    ),
                )
            )

    # Line items summing to subtotal is a SOFT signal — receipts legitimately
    # omit items, discounts, deposits — so info-level only.
    line_sum = sum(li.amount for li in r.line_items if li.amount is not None)
    if r.line_items and sub is not None and line_sum > 0 and not _close(line_sum, sub):
        issues.append(
            ValidationIssue(
                field="line_items",
                severity="info",
                message=(
                    f"Line items add to {line_sum:.2f}, subtotal reads "
                    f"{sub:.2f} — may be missing an item or a discount."
                ),
            )
        )

    # --- Field sanity -------------------------------------------------------
    if total is not None and total <= 0:
        issues.append(
            ValidationIssue(
                field="total",
                severity="warning",
                message="Total is zero or negative — please confirm.",
            )
        )

    if r.purchase_date and r.purchase_date > today:
        issues.append(
            ValidationIssue(
                field="purchase_date",
                severity="warning",
                message=f"Date {r.purchase_date} is in the future — please check.",
            )
        )

    if r.currency and r.currency not in KNOWN_CURRENCIES:
        issues.append(
            ValidationIssue(
                field="currency",
                severity="warning",
                message=f"'{r.currency}' isn't a currency code I recognize.",
            )
        )

    if r.is_receipt and r.total is None and "total" not in derived:
        issues.append(
            ValidationIssue(
                field="total",
                severity="error",
                message="No total could be read — please enter it before saving.",
            )
        )

    return ValidationReport(issues=issues, derived=derived)


def apply_report(r: ExtractedReceipt, report: ValidationReport) -> ExtractedReceipt:
    """Return a copy with derived fields filled in and all flagged fields merged
    into low_confidence_fields, so the review card highlights everything the
    checks surfaced — not just what the model self-reported."""
    updates = dict(report.derived)
    merged = list(
        dict.fromkeys([*r.low_confidence_fields, *report.flagged_fields()])
    )
    updates["low_confidence_fields"] = merged
    return r.model_copy(update=updates)
