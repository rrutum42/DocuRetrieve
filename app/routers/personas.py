"""Persona endpoints — the lightweight, no-auth profiles you pick on entry."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..api_models import Persona, PersonaCreate
from ..deps import get_repository
from ..repository import Repository

router = APIRouter(prefix="/api/personas", tags=["personas"])


@router.get("", response_model=list[Persona])
def list_personas(repo: Repository = Depends(get_repository)) -> list[Persona]:
    """Everyone on the profile-picker screen. Public by design — like choosing a
    profile on a shared family device."""
    return repo.list_personas()


@router.post("", response_model=Persona, status_code=201)
def create_persona(
    body: PersonaCreate, repo: Repository = Depends(get_repository)
) -> Persona:
    return repo.create_persona(body.name, body.color)
