"""Trip endpoints — the primary container. Every read enforces the visibility
rule via the acting persona (from the X-Persona-Id header)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..api_models import AddMembers, Persona, Receipt, Trip, TripCreate
from ..deps import current_persona, get_repository
from ..repository import Forbidden, NotFound, Repository

router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.get("", response_model=list[Trip])
def list_trips(
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
) -> list[Trip]:
    """Only trips this persona created or was shared into."""
    return repo.list_trips_for_persona(persona.id)


@router.post("", response_model=Trip, status_code=201)
def create_trip(
    body: TripCreate,
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
) -> Trip:
    return repo.create_trip(
        name=body.name,
        created_by=persona.id,
        start_date=body.start_date,
        end_date=body.end_date,
        cover_image=body.cover_image,
        member_ids=body.member_ids,
    )


@router.get("/{trip_id}", response_model=Trip)
def get_trip(
    trip_id: str,
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
) -> Trip:
    try:
        return repo.get_trip_for_persona(trip_id, persona.id)
    except NotFound:
        raise HTTPException(status_code=404, detail="Trip not found.")
    except Forbidden:
        # Don't leak existence to a persona who can't see it.
        raise HTTPException(status_code=404, detail="Trip not found.")


@router.get("/{trip_id}/receipts", response_model=list[Receipt])
def list_trip_receipts(
    trip_id: str,
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
) -> list[Receipt]:
    try:
        return repo.list_trip_receipts(trip_id, persona.id)
    except (NotFound, Forbidden):
        raise HTTPException(status_code=404, detail="Trip not found.")


@router.post("/{trip_id}/members", response_model=Trip)
def add_members(
    trip_id: str,
    body: AddMembers,
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
) -> Trip:
    try:
        return repo.add_trip_members(trip_id, persona.id, body.member_ids)
    except (NotFound, Forbidden):
        raise HTTPException(status_code=404, detail="Trip not found.")
