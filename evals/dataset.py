"""Labeled dataset for the validation-layer eval.

Each case is a receipt (as the model might return it) paired with the set of
fields that GENUINELY have a problem — the ground truth. The eval measures how
well `validate_receipt` recovers those flags (precision/recall).

This measures the *validator*, offline and deterministically. It does NOT measure
end-to-end extraction accuracy — that needs real labeled receipt images (see
evals/README.md). Both matter; this is the half we can run without images.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.schemas import ExtractedReceipt

FIXED_TODAY = date(2026, 7, 23)


@dataclass
class Case:
    name: str
    receipt: ExtractedReceipt
    expected_flags: set[str]  # fields that should be flagged (warning/error)
    note: str = ""


def _r(**kw) -> ExtractedReceipt:
    base = dict(is_receipt=True, currency="INR", purchase_date=date(2026, 6, 1))
    base.update(kw)
    return ExtractedReceipt(**base)


CASES: list[Case] = [
    # --- clean receipts: nothing should be flagged ------------------------
    Case("clean_inr", _r(subtotal=90, tax=10, total=100), set()),
    Case("clean_usd", _r(currency="USD", subtotal=42.10, tax=3.37, total=45.47), set()),
    Case("clean_eur_no_tax", _r(currency="EUR", subtotal=12.40, tax=0, total=12.40), set()),
    Case("clean_with_tip", _r(subtotal=80, tax=8, tip=12, total=100), set()),
    Case("clean_rounding_edge", _r(subtotal=33.34, tax=6.67, total=40.00), set(),
         "0.01 rounding — must NOT over-flag"),
    Case("clean_no_subtotal_derivable", _r(subtotal=None, tax=10, total=100), set(),
         "blank subtotal is derived, not an error"),
    Case("clean_big_amount", _r(subtotal=18000, tax=3240, total=21240), set()),

    # --- inconsistent totals: flag 'total' --------------------------------
    Case("total_misread_high", _r(subtotal=90, tax=10, total=130), {"total"},
         "90+10=100 but total 130"),
    Case("total_misread_low", _r(subtotal=90, tax=10, total=80), {"total"}),
    Case("total_digit_slip", _r(subtotal=250, tax=45, total=259), {"total"},
         "should be 295"),
    Case("total_ignores_tip", _r(subtotal=80, tax=8, tip=12, total=88), {"total"},
         "tip dropped from total"),
    Case("total_big_error", _r(subtotal=18000, tax=3240, total=2124), {"total"}),

    # --- sanity problems ---------------------------------------------------
    Case("future_date", _r(subtotal=90, tax=10, total=100, purchase_date=date(2027, 1, 1)),
         {"purchase_date"}),
    Case("bad_currency", _r(currency="XYZ", subtotal=90, tax=10, total=100), {"currency"}),
    Case("bad_currency_lowercase_real", _r(currency="usd", subtotal=90, tax=10, total=100),
         set(), "normalized to USD -> valid"),
    Case("zero_total", _r(subtotal=0, tax=0, total=0), {"total"}),
    Case("negative_total", _r(subtotal=-5, tax=0, total=-5), {"total"}),
    Case("missing_total_hard", _r(subtotal=None, tax=None, total=None), {"total"},
         "nothing to derive from -> hard error"),

    # --- combined problems -------------------------------------------------
    Case("future_and_inconsistent",
         _r(subtotal=90, tax=10, total=130, purchase_date=date(2028, 5, 5)),
         {"total", "purchase_date"}),
    Case("bad_currency_and_bad_total",
         _r(currency="ZZZ", subtotal=50, tax=5, total=70), {"currency", "total"}),

    # --- non-receipts: nothing to validate --------------------------------
    Case("non_receipt", ExtractedReceipt(is_receipt=False, rejection_reason="a dog"), set()),
]
