"""Receipt endpoints (Day 3): save a confirmed receipt (with its image), and
read the ledger for a container.

Flow: the client first calls /api/extract to get structured fields, shows the
always-confirm review card, then POSTs the confirmed fields here together with
the original image. Saving and extraction are separate so a user can correct the
model before anything is persisted.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from ..api_models import (
    AskRequest,
    AskResponse,
    DisputeRequest,
    LedgerSummary,
    Persona,
    Receipt,
    ReceiptCreate,
)
from ..ask import AskContext, AskPlanner, TripInfo, planner_error_response, run_query
from ..config import get_settings
from ..deps import (
    current_persona,
    get_ask_planner,
    get_fx,
    get_repository,
    get_storage,
)
from ..fx import FxService
from ..repository import Forbidden, NotFound, Repository
from ..schemas import Category, ExtractedReceipt
from ..storage import Storage
from ..summary import compute_summary
from ..validation import validate_receipt

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
    fx: FxService = Depends(get_fx),
) -> Receipt:
    """Persist a confirmed receipt and its original image.

    Converts the total into the container's base currency at the receipt's date
    (snapshot). Trip receipts use the trip's base currency; personal receipts use
    the app default. Conversion failures are non-fatal — the receipt saves with
    its native amount only.
    """
    mime = _validate_upload(file)  # reject non-image/PDF uploads first

    try:
        data = ReceiptCreate.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    # A receipt must record a real, positive amount. This is the server-side
    # backstop against saving a zero-cost row OR a non-receipt that slipped past
    # the reader (a photo of a koi pond has no total, so it can't be saved here).
    if data.total is None or data.total <= 0:
        raise HTTPException(
            status_code=422,
            detail="A receipt needs a total greater than 0. "
            "Enter the amount, or discard if this isn't a receipt.",
        )

    # Re-validate server-side and merge the flags into what we persist, so the
    # completeness/authenticity signal can't be stripped by a client POSTing
    # directly to hide a fabricated receipt (anti-fabrication, defense in depth).
    probe = ExtractedReceipt(
        is_receipt=True,
        merchant=data.merchant,
        purchase_date=data.purchase_date,
        currency=data.currency,
        subtotal=data.subtotal,
        tax=data.tax,
        tip=data.tip,
        total=data.total,
        category=data.category,
        payment_method=data.payment_method,
        line_items=[li.model_dump() for li in data.line_items],
        low_confidence_fields=data.low_confidence_fields,
    )
    report = validate_receipt(probe)
    data.low_confidence_fields = list(
        dict.fromkeys([*data.low_confidence_fields, *report.flagged_fields()])
    )

    image_bytes = await file.read()
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB).")

    # Determine the base currency for this container.
    if data.trip_id:
        try:
            trip = repo.get_trip_for_persona(data.trip_id, persona.id)
        except (NotFound, Forbidden):
            raise HTTPException(status_code=404, detail="Trip not found.")
        if data.paid_by_persona_id and data.paid_by_persona_id not in trip.member_ids:
            raise HTTPException(
                status_code=400, detail="paid_by must be a member of the trip."
            )
        base_currency = trip.base_currency
    else:
        base_currency = get_settings().default_base_currency

    # Snapshot-convert the total (best-effort; None on any failure).
    base_amount = fx_rate = fx_date = None
    if data.total is not None and data.currency:
        conv = fx.convert(data.total, data.currency, base_currency, data.purchase_date)
        if conv is not None:
            base_amount, fx_rate, fx_date = conv.base_amount, conv.fx_rate, conv.fx_date

    image_path = storage.upload_image(image_bytes, mime) if image_bytes else None

    try:
        return repo.create_receipt(
            owner_persona_id=persona.id,
            data=data,
            image_path=image_path,
            base_currency=base_currency,
            base_amount=base_amount,
            fx_rate=fx_rate,
            fx_date=fx_date,
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


@router.get("/personal/summary", response_model=LedgerSummary)
def personal_summary(
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
) -> LedgerSummary:
    receipts = repo.list_personal_receipts(persona.id)
    return compute_summary(receipts, get_settings().default_base_currency)


@router.post("/personal/ask", response_model=AskResponse)
def ask_personal(
    body: AskRequest,
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
    planner: AskPlanner = Depends(get_ask_planner),
) -> AskResponse:
    receipts = repo.list_personal_receipts(persona.id)
    base_currency = get_settings().default_base_currency
    ctx = AskContext(
        today=date.today(),
        base_currency=base_currency,
        categories=[c.value for c in Category],
        people=[persona.name],
    )
    trip_info = TripInfo(
        name="My Everyday",
        base_currency=base_currency,
        member_names=[persona.name],
        is_personal=True,
    )
    try:
        spec = planner.plan(body.question, ctx)
    except Exception as exc:
        return planner_error_response(body.question, exc)
    return run_query(
        body.question, spec, receipts, [persona], base_currency, trip_info=trip_info
    )


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


@router.post("/{receipt_id}/dispute", response_model=Receipt)
def dispute_receipt(
    receipt_id: str,
    body: DisputeRequest,
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
) -> Receipt:
    """Flag a receipt as untrustworthy. Any member who can see it may dispute —
    the social defense against fabricated claims in a shared trip."""
    try:
        return repo.set_dispute(receipt_id, persona.id, body.reason)
    except (NotFound, Forbidden):
        raise HTTPException(status_code=404, detail="Receipt not found.")


@router.delete("/{receipt_id}/dispute", response_model=Receipt)
def resolve_dispute(
    receipt_id: str,
    persona: Persona = Depends(current_persona),
    repo: Repository = Depends(get_repository),
) -> Receipt:
    """Clear a dispute (mark it resolved)."""
    try:
        return repo.set_dispute(receipt_id, persona.id, None)
    except (NotFound, Forbidden):
        raise HTTPException(status_code=404, detail="Receipt not found.")
