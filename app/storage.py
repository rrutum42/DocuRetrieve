"""Original-receipt image storage on Supabase Storage.

Images go into a PRIVATE bucket; we hand the frontend short-lived signed URLs
rather than public links, so one family's receipts aren't world-readable by
guessing a path. Signed-URL generation degrades gracefully — if it fails, the
receipt still lists, just without a thumbnail.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Protocol

BUCKET = "receipts"
SIGNED_URL_TTL = 3600  # seconds

_EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "application/pdf": "pdf",
}


@lru_cache
def _ensure_bucket_once(client) -> None:
    """Create the private bucket if it doesn't exist yet (idempotent)."""
    try:
        existing = {b.name for b in client.storage.list_buckets()}
        if BUCKET not in existing:
            client.storage.create_bucket(BUCKET, options={"public": False})
    except Exception:
        # Bucket may already exist, or the key lacks list perms but can still
        # read/write — don't block uploads on this best-effort check.
        pass


def upload_image(client, data: bytes, mime_type: str) -> str:
    """Store the image under a random key and return that key."""
    _ensure_bucket_once(client)
    ext = _EXT_BY_MIME.get(mime_type, "bin")
    key = f"{uuid.uuid4()}.{ext}"
    client.storage.from_(BUCKET).upload(
        key, data, {"content-type": mime_type, "upsert": "false"}
    )
    return key


def _extract_signed(resp) -> str | None:
    if isinstance(resp, dict):
        return resp.get("signedURL") or resp.get("signedUrl") or resp.get("signed_url")
    return None


def signed_url(client, key: str) -> str | None:
    if not key:
        return None
    try:
        resp = client.storage.from_(BUCKET).create_signed_url(key, SIGNED_URL_TTL)
        return _extract_signed(resp)
    except Exception:
        return None


def signed_urls(client, keys: list[str]) -> dict[str, str]:
    """Batch variant; falls back to per-key on any failure."""
    keys = [k for k in keys if k]
    if not keys:
        return {}
    try:
        resp = client.storage.from_(BUCKET).create_signed_urls(keys, SIGNED_URL_TTL)
        out: dict[str, str] = {}
        for item in resp or []:
            path = item.get("path")
            url = _extract_signed(item)
            if path and url:
                out[path] = url
        if out:
            return out
    except Exception:
        pass
    return {k: url for k in keys if (url := signed_url(client, k))}


# --------------------------------------------------------------------------- #
# Injectable storage seam (so writes are testable without real object storage)
# --------------------------------------------------------------------------- #

class Storage(Protocol):
    def upload_image(self, data: bytes, mime_type: str) -> str | None: ...


class SupabaseStorage:
    def __init__(self, client) -> None:
        self._client = client

    def upload_image(self, data: bytes, mime_type: str) -> str | None:
        return upload_image(self._client, data, mime_type)


class NoopStorage:
    """No object storage available (tests / no-Supabase dev). Receipts save
    without a stored image."""

    def upload_image(self, data: bytes, mime_type: str) -> str | None:
        return None
