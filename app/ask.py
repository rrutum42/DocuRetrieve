"""Natural-language questions over a container's receipts.

Design: the model does NOT run SQL. It translates the question into a small,
validated QuerySpec (a filter + an aggregation). We then execute that spec in
Python over the receipts we already loaded (with visibility enforced upstream).
This is injection-proof, gives exact arithmetic, and lets us return the exact
receipts behind every answer.

The model call is behind an AskPlanner seam so tests run without Gemini.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from .api_models import AskResponse, Persona, Receipt
from .schemas import Category

Operation = Literal["sum", "count", "average", "max", "min", "list", "balance"]

_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


class QuerySpec(BaseModel):
    """The structured plan a question is compiled into."""

    operation: Operation = "sum"
    category: Category | None = None
    paid_by: str | None = Field(
        default=None, description="A person's name, if the question is about one payer."
    )
    currency: str | None = Field(
        default=None, description="Native ISO currency to filter by, e.g. USD."
    )
    merchant_contains: str | None = None
    date_from: date | None = None
    date_to: date | None = None


class AskPlanner(Protocol):
    def plan(self, question: str, context: "AskContext") -> QuerySpec: ...


class AskContext(BaseModel):
    today: date
    base_currency: str
    categories: list[str]
    people: list[str]


# --------------------------------------------------------------------------- #
# Execution (pure, deterministic)
# --------------------------------------------------------------------------- #

def _money(value: float, currency: str) -> str:
    sym = _SYMBOLS.get(currency, "")
    body = f"{value:,.2f}"
    return f"{sym}{body}" if sym else f"{body} {currency}"


def _resolve_persona(name: str, personas: list[Persona]) -> str | None:
    n = name.strip().lower()
    for p in personas:
        if p.name.strip().lower() == n:
            return p.id
    for p in personas:  # looser contains match
        if n in p.name.strip().lower():
            return p.id
    return None


def _filter(spec: QuerySpec, receipts: list[Receipt], personas: list[Persona]):
    out = receipts
    if spec.category is not None:
        out = [r for r in out if r.category == spec.category]
    if spec.currency:
        cur = spec.currency.strip().upper()
        out = [r for r in out if (r.currency or "").upper() == cur]
    if spec.merchant_contains:
        m = spec.merchant_contains.lower()
        out = [r for r in out if r.merchant and m in r.merchant.lower()]
    if spec.date_from:
        out = [r for r in out if r.purchase_date and r.purchase_date >= spec.date_from]
    if spec.date_to:
        out = [r for r in out if r.purchase_date and r.purchase_date <= spec.date_to]
    if spec.paid_by:
        pid = _resolve_persona(spec.paid_by, personas)
        out = [r for r in out if r.paid_by_persona_id == pid] if pid else []
    return out


def _describe(spec: QuerySpec, personas: list[Persona]) -> str:
    bits = []
    if spec.category is not None:
        bits.append(f"on {spec.category.value}")
    if spec.currency:
        bits.append(f"in {spec.currency.upper()}")
    if spec.merchant_contains:
        bits.append(f"at {spec.merchant_contains}")
    if spec.paid_by:
        bits.append(f"paid by {spec.paid_by}")
    if spec.date_from and spec.date_to:
        bits.append(f"between {spec.date_from} and {spec.date_to}")
    elif spec.date_from:
        bits.append(f"since {spec.date_from}")
    elif spec.date_to:
        bits.append(f"through {spec.date_to}")
    return (" " + " ".join(bits)) if bits else ""


def _persona_name(pid: str, personas: list[Persona]) -> str:
    for p in personas:
        if p.id == pid:
            return p.name
    return "They"


def _answer_balance(
    question: str,
    spec: QuerySpec,
    receipts: list[Receipt],
    personas: list[Persona],
    base_currency: str,
    member_ids: list[str] | None,
) -> AskResponse:
    resp = dict(question=question, operation="balance", currency=base_currency, value=None)
    if not member_ids:
        return AskResponse(
            **{**resp, "currency": None},
            answer="Settle-up applies to trips with more than one person.",
            matched=[],
        )
    if not spec.paid_by:
        return AskResponse(
            **{**resp, "currency": None},
            answer="Who do you mean? Ask about a specific person, e.g. 'how much is owed to Bob'.",
            matched=[],
        )
    pid = _resolve_persona(spec.paid_by, personas)
    if pid is None or pid not in member_ids:
        return AskResponse(
            **{**resp, "currency": None},
            answer=f"{spec.paid_by} isn't on this trip.",
            matched=[],
        )

    total = sum(r.base_amount for r in receipts if r.base_amount is not None)
    fair_share = total / len(member_ids)
    paid = sum(
        r.base_amount
        for r in receipts
        if r.paid_by_persona_id == pid and r.base_amount is not None
    )
    net = round(paid - fair_share, 2)
    name = _persona_name(pid, personas)
    their = [r for r in receipts if r.paid_by_persona_id == pid]

    if abs(net) < 0.01:
        answer = f"{name} is settled up — no money owed either way."
    elif net > 0:
        answer = (
            f"{name} is owed {_money(net, base_currency)} "
            f"(paid {_money(round(paid, 2), base_currency)}, "
            f"fair share {_money(round(fair_share, 2), base_currency)})."
        )
    else:
        answer = (
            f"{name} owes {_money(-net, base_currency)} "
            f"(paid {_money(round(paid, 2), base_currency)}, "
            f"fair share {_money(round(fair_share, 2), base_currency)})."
        )
    return AskResponse(**{**resp, "value": net}, answer=answer, matched=their)


def run_query(
    question: str,
    spec: QuerySpec,
    receipts: list[Receipt],
    personas: list[Persona],
    base_currency: str,
    member_ids: list[str] | None = None,
) -> AskResponse:
    if spec.operation == "balance":
        return _answer_balance(
            question, spec, receipts, personas, base_currency, member_ids
        )

    matched = _filter(spec, receipts, personas)
    amounts = [r.base_amount for r in matched if r.base_amount is not None]
    desc = _describe(spec, personas)
    n = len(matched)
    resp = dict(question=question, operation=spec.operation, currency=None, value=None)

    if n == 0:
        return AskResponse(**resp, answer=f"No receipts found{desc}.", matched=[])

    if spec.operation == "count":
        answer = f"{n} receipt{'s' if n != 1 else ''}{desc}."
        return AskResponse(**{**resp, "value": float(n)}, answer=answer, matched=matched)

    if spec.operation == "list":
        answer = f"{n} receipt{'s' if n != 1 else ''}{desc}."
        return AskResponse(**resp, answer=answer, matched=matched)

    if spec.operation == "average":
        if not amounts:
            return AskResponse(**resp, answer=f"No convertible amounts{desc}.", matched=matched)
        avg = round(sum(amounts) / len(amounts), 2)
        answer = f"Average {_money(avg, base_currency)}{desc}, across {len(amounts)} receipts."
        return AskResponse(
            **{**resp, "value": avg, "currency": base_currency}, answer=answer, matched=matched
        )

    if spec.operation in ("max", "min"):
        convertible = [r for r in matched if r.base_amount is not None]
        if not convertible:
            return AskResponse(**resp, answer=f"No convertible amounts{desc}.", matched=matched)
        pick = (max if spec.operation == "max" else min)(
            convertible, key=lambda r: r.base_amount
        )
        label = "Largest" if spec.operation == "max" else "Smallest"
        where = f" at {pick.merchant}" if pick.merchant else ""
        when = f" on {pick.purchase_date}" if pick.purchase_date else ""
        answer = f"{label}{desc}: {_money(pick.base_amount, base_currency)}{where}{when}."
        return AskResponse(
            **{**resp, "value": pick.base_amount, "currency": base_currency},
            answer=answer,
            matched=[pick],
        )

    # default: sum
    total = round(sum(amounts), 2)
    note = ""
    if len(amounts) < n:
        skipped = n - len(amounts)
        note = f" ({skipped} not converted, excluded)"
    answer = (
        f"{_money(total, base_currency)} spent{desc}, "
        f"across {len(amounts)} receipt{'s' if len(amounts) != 1 else ''}{note}."
    )
    return AskResponse(
        **{**resp, "value": total, "currency": base_currency}, answer=answer, matched=matched
    )


# --------------------------------------------------------------------------- #
# Planners (question -> QuerySpec)
# --------------------------------------------------------------------------- #

PLANNER_PROMPT = """You turn a question about trip receipts into a JSON query spec.

Context:
- Today is {today}.
- Amounts roll up into {base_currency}.
- Categories available: {categories}.
- People on this ledger: {people}.

Rules:
- Pick the single best operation:
    sum      -> "how much" (default)
    count    -> "how many", "is there any"
    average  -> "average / typical"
    max      -> "biggest / most expensive"
    min      -> "cheapest / smallest"
    list     -> "show me / which"
    balance  -> settle-up: "how much is owed to X", "how much does X owe", "is X settled up"
- For a balance question, set paid_by to the person the question is about.
- Only set category to one of the listed categories, else leave null.
- paid_by must be one of the listed people, else null.
- currency: an ISO code (e.g. USD, EUR) if the question is about expenses in a
  specific currency ("in dollars", "any USD expenses"), else null.
- Resolve relative dates ("last month", "in June", "this week") to date_from/date_to
  using today's date. Leave both null if no time filter.
- merchant_contains: a store/vendor name if the question names one, else null.
Return ONLY the JSON."""


class GeminiPlanner:
    """Live planner using Gemini structured output."""

    def plan(self, question: str, context: AskContext) -> QuerySpec:
        from google import genai
        from google.genai import types

        from .config import get_settings

        settings = get_settings()
        client = genai.Client(api_key=settings.gemini_api_key)
        model = settings.gemini_ask_model or settings.gemini_model
        prompt = PLANNER_PROMPT.format(
            today=context.today.isoformat(),
            base_currency=context.base_currency,
            categories=", ".join(context.categories),
            people=", ".join(context.people) or "(none)",
        )
        resp = client.models.generate_content(
            model=model,
            contents=[prompt, f"Question: {question}"],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=QuerySpec,
                temperature=0,
            ),
        )
        return QuerySpec.model_validate_json(resp.text or "{}")


class ListAllPlanner:
    """Fallback when no LLM is configured — just lists everything."""

    def plan(self, question: str, context: AskContext) -> QuerySpec:
        return QuerySpec(operation="list")


def planner_error_response(question: str, exc: Exception) -> AskResponse:
    """Honest response when the planner can't run (rate limit / outage) — instead
    of silently pretending we understood and listing everything."""
    msg = str(exc)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        answer = "The assistant is briefly rate-limited. Please try again in a moment."
    else:
        answer = "Sorry, I couldn't process that question just now. Try rephrasing it."
    return AskResponse(
        question=question, operation="unavailable", value=None, answer=answer, matched=[]
    )
