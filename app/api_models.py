"""API request/response models for personas and trips (Day 2).

Kept separate from schemas.py (which is the model-extraction contract) so the
two concerns don't bleed together.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from .schemas import Category


# --- Personas ---------------------------------------------------------------

class PersonaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    color: str | None = None


class Persona(BaseModel):
    id: str
    name: str
    color: str | None = None
    created_at: datetime | None = None


# --- Trips ------------------------------------------------------------------

class TripCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    start_date: date | None = None
    end_date: date | None = None
    cover_image: str | None = None
    member_ids: list[str] = Field(
        default_factory=list,
        description="Persona ids to share the trip with. The creator is always a member.",
    )


class Trip(BaseModel):
    id: str
    name: str
    start_date: date | None = None
    end_date: date | None = None
    cover_image: str | None = None
    created_by: str
    member_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class AddMembers(BaseModel):
    member_ids: list[str] = Field(min_length=1)


# --- Receipts ---------------------------------------------------------------

class ReceiptLineItem(BaseModel):
    description: str
    qty: float | None = None
    unit_price: float | None = None
    amount: float | None = None


class ReceiptCreate(BaseModel):
    """The confirmed receipt the user saves after reviewing the extraction.

    trip_id is None for the personal ("Everyday") ledger. paid_by defaults to
    the uploader if the client doesn't set it.
    """

    trip_id: str | None = None
    paid_by_persona_id: str | None = None
    merchant: str | None = None
    purchase_date: date | None = None
    currency: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    tip: float | None = None
    total: float | None = None
    category: Category | None = None
    payment_method: str | None = None
    line_items: list[ReceiptLineItem] = Field(default_factory=list)
    low_confidence_fields: list[str] = Field(default_factory=list)
    raw_extraction: dict | None = None


class Receipt(BaseModel):
    id: str
    trip_id: str | None = None
    owner_persona_id: str
    paid_by_persona_id: str
    merchant: str | None = None
    purchase_date: date | None = None
    currency: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    tip: float | None = None
    total: float | None = None
    category: Category | None = None
    payment_method: str | None = None
    line_items: list[ReceiptLineItem] = Field(default_factory=list)
    low_confidence_fields: list[str] = Field(default_factory=list)
    image_path: str | None = None
    image_url: str | None = None  # signed, generated at read time
    status: str = "confirmed"
    created_at: datetime | None = None
