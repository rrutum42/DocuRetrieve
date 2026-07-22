"""FastAPI application.

Day 1 surface: health, a config probe (drives the first-run UI), and the
extraction endpoint that turns an uploaded image into a structured, reviewable
receipt. Persistence, trips, personas, and the ask endpoint arrive on later days.

In production this same process also serves the built React app from
frontend/dist, so the whole thing is a single Render deploy.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .extraction import extract_receipt
from .routers import personas, trips
from .schemas import ExtractionResult

app = FastAPI(title="DocuRetrieve", version="0.1.0")

# In dev the React app runs on Vite (port 5173) and calls this API on 8000.
# In production the same process serves the built frontend, so CORS is moot.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(personas.router)
app.include_router(trips.router)

ACCEPTED_MIME_PREFIXES = ("image/",)
ACCEPTED_MIME_EXACT = ("application/pdf",)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB — a phone photo is well under this.


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": app.version}


@app.get("/api/config")
def config() -> dict:
    """Tells the frontend what's wired up, so first-run can guide setup instead
    of failing cryptically."""
    settings = get_settings()
    return {
        "gemini_configured": settings.gemini_configured,
        "supabase_configured": settings.supabase_configured,
        "using_stub": settings.docuretrieve_use_stub or not settings.gemini_configured,
    }


@app.post("/api/extract", response_model=ExtractionResult)
async def extract(file: UploadFile = File(...)) -> ExtractionResult:
    """Read one uploaded receipt into structured, reviewable data.

    This does NOT persist anything — it returns the extraction so the frontend
    can show the always-confirm review card. Saving happens after the user
    confirms (Day 3).
    """
    mime = file.content_type or ""
    is_accepted = mime.startswith(ACCEPTED_MIME_PREFIXES) or mime in ACCEPTED_MIME_EXACT
    if not is_accepted:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{mime}'. Upload an image or PDF.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
        )

    return extract_receipt(data, mime)


# --------------------------------------------------------------------------- #
# Serve the built frontend (if present) so this is a single deploy.
#
# Registered last so /api/* and the docs always win. Hashed assets are served
# from /assets; every other non-API path falls back to index.html so client-side
# routes (e.g. /trip/:id) survive a direct load or refresh (SPA fallback).
# --------------------------------------------------------------------------- #
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=_frontend_dist / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")
        candidate = _frontend_dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)  # favicon, etc.
        return FileResponse(_frontend_dist / "index.html")
