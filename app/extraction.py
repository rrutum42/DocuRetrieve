"""Receipt extraction — the one hard step, collapsed into a single model call.

Gemini's vision model reads the raw pixels of a receipt photo/PDF and returns
structured JSON (OCR + extraction in one shot). This module wraps that call with
the parts that make it trustworthy:

  * strict schema validation (app.schemas.ExtractedReceipt)
  * a bounded retry when the model emits malformed JSON
  * a graceful fallback that never crashes the upload
  * a `generate` seam so tests (and the --stub mode) run with no API key

The prompt is engineered around the messy real world: bad photos, foreign
currencies, partial receipts, and non-receipts.
"""

from __future__ import annotations

from typing import Callable, Protocol

from pydantic import ValidationError

from .config import get_settings
from .schemas import ExtractedReceipt, ExtractionResult
from .validation import apply_report, validate_receipt

MAX_ATTEMPTS = 2

EXTRACTION_PROMPT = """You are a meticulous receipt-reading assistant for a family expense app.

Look at the attached image or PDF and extract the receipt as JSON matching the
provided schema. Rules:

1. First decide: is this actually a receipt/invoice/bill? If it is NOT (a selfie,
   a menu, a random photo, a blank page), set "is_receipt": false and give a short
   "rejection_reason". Do not invent receipt fields for a non-receipt.
2. Normalize the purchase date to YYYY-MM-DD. If you cannot read it, use null and
   add "purchase_date" to low_confidence_fields.
3. currency must be an ISO 4217 code (USD, EUR, INR, ...). Infer it from the symbol,
   language, or country if not printed.
4. Never guess a total. If the total is unreadable or torn off, use null and add
   "total" to low_confidence_fields. It is better to say "unsure" than to be wrong.
5. Add ANY field you are not confident about to low_confidence_fields so a human
   can review it.
6. Choose the single best category from the allowed list.
7. Extract line items when they are legible; skip them if they are not.

Return ONLY the JSON object."""


class GenerateFn(Protocol):
    """A callable that turns image bytes into raw model JSON text."""

    def __call__(self, image_bytes: bytes, mime_type: str) -> str: ...


# --------------------------------------------------------------------------- #
# Real Gemini backend (lazily imported so tests/stub need no SDK or key)
# --------------------------------------------------------------------------- #

_client = None


def _gemini_generate(image_bytes: bytes, mime_type: str) -> str:
    """Call Gemini's multimodal model and return the raw JSON string."""
    global _client
    settings = get_settings()

    if _client is None:
        from google import genai  # lazy: only needed for real calls

        _client = genai.Client(api_key=settings.gemini_api_key)

    from google.genai import types

    response = _client.models.generate_content(
        model=settings.gemini_model,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            EXTRACTION_PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractedReceipt,
            temperature=0,
        ),
    )
    return response.text or ""


def _stub_generate(image_bytes: bytes, mime_type: str) -> str:
    """Deterministic stand-in so the app and tests run with no API key.

    Returns a plausible confirmed-looking receipt. Real extraction quality is
    exercised by the fixture-backed tests, not this stub.
    """
    return ExtractedReceipt(
        is_receipt=True,
        merchant="Stub Grocery Co.",
        purchase_date="2026-07-20",
        currency="USD",
        subtotal=18.50,
        tax=1.50,
        total=20.00,
        category="groceries",
        payment_method="card",
        line_items=[{"description": "Milk", "qty": 1, "amount": 3.50}],
        low_confidence_fields=[],
        notes="stubbed extraction",
    ).model_dump_json()


def _default_generate() -> GenerateFn:
    settings = get_settings()
    if settings.docuretrieve_use_stub or not settings.gemini_configured:
        return _stub_generate
    return _gemini_generate


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def extract_receipt(
    image_bytes: bytes,
    mime_type: str,
    *,
    generate: Callable[[bytes, str], str] | None = None,
) -> ExtractionResult:
    """Extract one receipt, with bounded retry and a safe fallback.

    Never raises for a bad model response: on repeated malformed JSON it returns
    an ExtractionResult with receipt=None and used_fallback=True, so the caller
    can route the upload into manual review instead of dropping it.
    """
    gen = generate or _default_generate()

    last_raw = ""
    last_error: str | None = None

    for _attempt in range(MAX_ATTEMPTS):
        try:
            last_raw = gen(image_bytes, mime_type)
        except Exception as exc:  # network / rate-limit / SDK error
            last_error = f"generation_error: {exc}"
            continue

        try:
            receipt = ExtractedReceipt.model_validate_json(last_raw)
        except ValidationError as exc:
            last_error = f"validation_error: {exc.error_count()} issue(s)"
            continue

        # Independently check the model's work: derive blank fields via safe
        # algebra, flag inconsistencies for the human review step.
        report = validate_receipt(receipt)
        receipt = apply_report(receipt, report)
        return ExtractionResult(
            receipt=receipt, raw=last_raw, used_fallback=False, validation=report
        )

    # Exhausted attempts — hand back a reviewable failure, don't crash the upload.
    return ExtractionResult(
        receipt=None,
        raw=last_raw,
        used_fallback=True,
        error=last_error or "extraction_failed",
    )
