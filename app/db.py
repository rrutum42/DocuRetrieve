"""Supabase client accessor.

Kept intentionally thin for Day 1 — it just hands back a configured client (or
raises a clear error if Supabase isn't configured yet). Query helpers and the
server-side visibility rule land on Day 2 when the trip/persona endpoints arrive.
"""

from __future__ import annotations

from functools import lru_cache

from .config import get_settings


@lru_cache
def get_supabase():
    """Return a cached Supabase client, or raise if not configured."""
    settings = get_settings()
    if not settings.supabase_configured:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY in .env "
            "(see .env.example)."
        )
    from supabase import create_client  # lazy import

    return create_client(settings.supabase_url, settings.supabase_key)
