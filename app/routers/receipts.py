"""Receipt endpoints (Day 3): save a confirmed receipt (with its image), and
read the ledger for a container.

Flow: the client first calls /api/extract to get structured fields, shows the
always-confirm review card, then POSTs the confirmed fields here together with
the original image. Saving and extraction are separate so a user can correct the
model before anything is persisted.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from ..api_models import Persona, Receipt, ReceiptCreate
from ..deps import current_persona, get_repository, get_storage
from ..repository import Forbidden, NotFound, Repository
from ..storage import Storage

router = APIRouter(prefix="/api/receipts", tags=["receipts"])

ACCEPTED_MIME_PREFIXES = ("image/",)
ACCEPTED_MIME_EXACT = ("application/pdf",)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _validate_upload(file: UploadFile) -> str:
    mime = file.content_type or ""
    if not (mime.startswith(ACCEPTED_MIME_PREFIXES) or mime in ACCEPTED_MIME_EXACT):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{mime}'. Upload an image or PDF.",
        )
    return mime


@router.post("", response_model=Receipt, status_code=201)
async def create_receipt(
    payload: str = Form(..., description="JSON body matching ReceiptCreate"),
    file: UploadFile = File(...),
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> Receipt:
    """Persist a confirmed receipt and its original image."""
    try:
        data = ReceiptCreate.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    mime = _validate_upload(file)
    image_bytes = await file.read()
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB).")

    # paid_by must be someone actually on the trip.
    if data.trip_id and data.paid_by_persona_id:
        try:
            trip = repo.get_trip_for_persona(data.trip_id, persona.id)
        except (NotFound, Forbidden):
            raise HTTPException(status_code=404, detail="Trip not found.")
        if data.paid_by_persona_id not in trip.member_ids:
            raise HTTPException(
                status_code=400, detail="paid_by must be a member of the trip."
            )

    image_path = storage.upload_image(image_bytes, mime) if image_bytes else None

    try:
        return repo.create_receipt(
            owner_persona_id=persona.id, data=data, image_path=image_path
        )
    except (NotFound, Forbidden):
        raise HTTPException(status_code=404, detail="Trip not found.")


@router.get("/personal", response_model=list[Receipt])
def list_personal(
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
) -> list[Receipt]:
    """The acting persona's private, trip-less 'Everyday' ledger."""
    return repo.list_personal_receipts(persona.id)


@router.get("/{receipt_id}", response_model=Receipt)
def get_receipt(
    receipt_id: str,
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
) -> Receipt:
    try:
        return repo.get_receipt(receipt_id, persona.id)
    except (NotFound, Forbidden):
        raise HTTPException(status_code=404, detail="Receipt not found.")


@router.delete("/{receipt_id}", status_code=204)
def delete_receipt(
    receipt_id: str,
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
) -> None:
    try:
        repo.delete_receipt(receipt_id, persona.id)
    except (NotFound, Forbidden):
        raise HTTPException(status_code=404, detail="Receipt not found.")
