"""Shared test helpers.

Extraction tests never touch the network or the Gemini SDK — they inject a fake
`generate` function via the `generate=` seam on extract_receipt. Fixtures below
are recorded, representative model responses (the good, the messy, and the bad).
"""

from __future__ import annotations

import json
from typing import Callable


def fixed_response(payload: dict | str) -> Callable[[bytes, str], str]:
    """A generate fn that always returns the given JSON (dict or raw string)."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)

    def _generate(image_bytes: bytes, mime_type: str) -> str:
        return raw

    return _generate


def scripted_responses(*payloads) -> Callable[[bytes, str], str]:
    """A generate fn that returns each payload in turn (to exercise retry)."""
    queue = [p if isinstance(p, str) else json.dumps(p) for p in payloads]
    idx = {"i": 0}

    def _generate(image_bytes: bytes, mime_type: str) -> str:
        i = min(idx["i"], len(queue) - 1)
        idx["i"] += 1
        return queue[i]

    return _generate


def raising_generate(exc: Exception) -> Callable[[bytes, str], str]:
    """A generate fn that always raises (simulates a rate limit / timeout)."""

    def _generate(image_bytes: bytes, mime_type: str) -> str:
        raise exc

    return _generate


# --- Recorded, representative model responses --------------------------------

CLEAN_RECEIPT = {
    "is_receipt": True,
    "merchant": "Whole Foods Market",
    "purchase_date": "2026-07-15",
    "currency": "USD",
    "subtotal": 42.10,
    "tax": 3.37,
    "tip": None,
    "total": 45.47,
    "category": "groceries",
    "payment_method": "Visa ****1234",
    "line_items": [
        {"description": "Bananas", "qty": 1, "unit_price": 1.20, "amount": 1.20},
        {"description": "Oat Milk", "qty": 2, "unit_price": 3.99, "amount": 7.98},
    ],
    "low_confidence_fields": [],
    "notes": None,
}

FOREIGN_CURRENCY_RECEIPT = {
    "is_receipt": True,
    "merchant": "Boulangerie Paul",
    "purchase_date": "2026-06-02",
    "currency": "eur",  # lower-case on purpose — validator should upper it
    "subtotal": 12.40,
    "tax": None,
    "total": 12.40,
    "category": "dining",
    "payment_method": None,
    "line_items": [],
    "low_confidence_fields": ["tax"],
    "notes": "French receipt, tax not itemized",
}

NON_RECEIPT = {
    "is_receipt": False,
    "rejection_reason": "This looks like a photo of a dog, not a receipt.",
    "merchant": None,
    "purchase_date": None,
    "currency": None,
    "total": None,
    "category": None,
    "line_items": [],
    "low_confidence_fields": [],
    "notes": None,
}

PARTIAL_RECEIPT_NO_TOTAL = {
    "is_receipt": True,
    "merchant": "Shell",
    "purchase_date": None,
    "currency": "USD",
    "subtotal": None,
    "total": None,  # torn off — model must NOT invent it
    "category": "fuel",
    "payment_method": None,
    "line_items": [],
    "low_confidence_fields": ["purchase_date", "total"],
    "notes": "Bottom of receipt torn.",
}
