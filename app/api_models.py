"""API request/response models for personas and trips (Day 2).

Kept separate from schemas.py (which is the model-extraction contract) so the
two concerns don't bleed together.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


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
