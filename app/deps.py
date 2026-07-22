"""FastAPI dependencies: the repository and the current persona.

There is no real auth by design. The client sends the selected persona's id in
the `X-Persona-Id` header; the server validates it exists and uses it as the
visibility key for every trip query. This keeps the "no auth, but still
enforced" model honest — the enforcement is server-side, not in the UI.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Header, HTTPException

from .api_models import Persona
from .config import get_settings
from .repository import InMemoryRepository, Repository, SupabaseRepository
from .storage import NoopStorage, Storage, SupabaseStorage


@lru_cache
def get_repository() -> Repository:
    """Live: Supabase when configured. Otherwise an in-memory store so the app
    still runs locally without a database (data is not persisted)."""
    settings = get_settings()
    if settings.supabase_configured:
        from .db import get_supabase

        return SupabaseRepository(get_supabase())
    return InMemoryRepository()


@lru_cache
def get_storage() -> Storage:
    """Live: Supabase Storage. Otherwise a no-op so receipts still save (sans
    image) with no object storage configured."""
    settings = get_settings()
    if settings.supabase_configured:
        from .db import get_supabase

        return SupabaseStorage(get_supabase())
    return NoopStorage()


def current_persona(
    x_persona_id: str | None = Header(default=None),
    repo: Repository = Depends(get_repository),
) -> Persona:
    """Resolve and validate the acting persona from the X-Persona-Id header."""
    if not x_persona_id:
        raise HTTPException(
            status_code=401,
            detail="No persona selected. Send an X-Persona-Id header.",
        )
    persona = repo.get_persona(x_persona_id)
    if persona is None:
        raise HTTPException(status_code=401, detail="Unknown persona.")
    return persona
