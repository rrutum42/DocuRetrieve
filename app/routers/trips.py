"""Trip endpoints — the primary container. Every read enforces the visibility
rule via the acting persona (from the X-Persona-Id header)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from ..api_models import (
    AddMembers,
    AskRequest,
    AskResponse,
    LedgerSummary,
    Persona,
    Receipt,
    Trip,
    TripCreate,
)
from ..ask import AskContext, AskPlanner, TripInfo, planner_error_response, run_query
from ..deps import current_persona, get_ask_planner, get_repository
from ..repository import Forbidden, NotFound, Repository
from ..schemas import Category
from ..summary import compute_summary

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
        base_currency=(body.base_currency or "INR").upper(),
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


@router.get("/{trip_id}/summary", response_model=LedgerSummary)
def trip_summary(
    trip_id: str,
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
) -> LedgerSummary:
    """Grand total + per-person 'who paid' split, in the trip's base currency."""
    try:
        trip = repo.get_trip_for_persona(trip_id, persona.id)
        receipts = repo.list_trip_receipts(trip_id, persona.id)
    except (NotFound, Forbidden):
        raise HTTPException(status_code=404, detail="Trip not found.")
    return compute_summary(receipts, trip.base_currency, member_ids=trip.member_ids)


@router.post("/{trip_id}/ask", response_model=AskResponse)
def ask_trip(
    trip_id: str,
    body: AskRequest,
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
    planner: AskPlanner = Depends(get_ask_planner),
) -> AskResponse:
    """Answer a natural-language question over this trip's receipts."""
    try:
        trip = repo.get_trip_for_persona(trip_id, persona.id)
        receipts = repo.list_trip_receipts(trip_id, persona.id)
    except (NotFound, Forbidden):
        raise HTTPException(status_code=404, detail="Trip not found.")

    personas = repo.list_personas()
    # Give the planner ALL persona names (they're public on the picker), not just
    # trip members — otherwise a question about a non-member ("how much did Bob
    # pay" when Bob isn't on the trip) can't bind paid_by, and the payer filter
    # silently drops, turning it into a whole-trip sum. Membership is still
    # enforced separately via member_ids (e.g. for settle-up).
    ctx = AskContext(
        today=date.today(),
        base_currency=trip.base_currency,
        categories=[c.value for c in Category],
        people=[p.name for p in personas],
        history=body.history,
    )
    by_id = {p.id: p for p in personas}
    trip_info = TripInfo(
        name=trip.name,
        base_currency=trip.base_currency,
        member_names=[by_id[m].name for m in trip.member_ids if m in by_id],
        start_date=trip.start_date,
        end_date=trip.end_date,
        is_personal=False,
    )
    try:
        spec = planner.plan(body.question, ctx)
    except Exception as exc:
        return planner_error_response(body.question, exc)
    return run_query(
        body.question,
        spec,
        receipts,
        personas,
        trip.base_currency,
        member_ids=trip.member_ids,
        trip_info=trip_info,
    )


@router.delete("/{trip_id}", status_code=204)
def delete_trip(
    trip_id: str,
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
) -> None:
    """Delete a trip and all its receipts. Only the creator may do this."""
    try:
        trip = repo.get_trip_for_persona(trip_id, persona.id)
    except (NotFound, Forbidden):
        raise HTTPException(status_code=404, detail="Trip not found.")
    if trip.created_by != persona.id:
        raise HTTPException(
            status_code=403, detail="Only the trip's creator can delete it."
        )
    repo.delete_trip(trip_id, persona.id)


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
