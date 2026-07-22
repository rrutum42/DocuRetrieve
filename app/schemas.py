"""Pydantic schemas — the contract between the model, the API, and the DB.

The extraction schema is deliberately strict: the model must tell us whether the
image is even a receipt, and must flag its own low-confidence fields so the UI
can highlight them for the always-confirm review step.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Category(str, Enum):
    groceries = "groceries"
    dining = "dining"
    fuel = "fuel"
    lodging = "lodging"
    transport = "transport"
    shopping = "shopping"
    other = "other"


class LineItem(BaseModel):
    description: str
    qty: float | None = None
    unit_price: float | None = None
    amount: float | None = None


class ExtractedReceipt(BaseModel):
    """What Gemini returns for one uploaded image.

    `is_receipt=False` is a first-class, valid outcome — not an error. It is how
    we reject non-receipts (a selfie, a menu, a blank page) without writing a
    garbage row.
    """

    is_receipt: bool
    rejection_reason: str | None = Field(
        default=None,
        description="Set only when is_receipt is False — a short human explanation.",
    )

    merchant: str | None = None
    purchase_date: date | None = Field(
        default=None, description="Normalized to YYYY-MM-DD, or null if unreadable."
    )
    currency: str | None = Field(
        default=None, description="ISO 4217 code, e.g. USD, EUR, INR."
    )
    subtotal: float | None = None
    tax: float | None = None
    tip: float | None = None
    total: float | None = None
    category: Category | None = None
    payment_method: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)

    low_confidence_fields: list[str] = Field(
        default_factory=list,
        description="Names of fields the model was unsure about; the UI flags these.",
    )
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def _normalize_currency(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        return v or None

    @field_validator("purchase_date", mode="before")
    @classmethod
    def _blank_date_to_none(cls, v):
        # The model sometimes emits "" or "unknown" instead of null.
        if isinstance(v, str) and v.strip().lower() in {"", "unknown", "n/a", "null"}:
            return None
        return v


class ExtractionResult(BaseModel):
    """The extraction pipeline's output, wrapping the parsed receipt with metadata
    the caller needs: the raw model text (stored for audit) and whether we had to
    fall back after a validation failure."""

    receipt: ExtractedReceipt | None
    raw: str
    used_fallback: bool = False
    error: str | None = None
