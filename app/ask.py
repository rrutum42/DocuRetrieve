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

from .api_models import AskResponse, AskTurn, BreakdownRow, Persona, Receipt
from .schemas import Category

Operation = Literal[
    "sum", "count", "average", "max", "min", "list",
    "balance", "members", "overview", "breakdown", "compare", "unsupported",
]

GroupBy = Literal["category", "paid_by", "currency", "merchant"]
Sort = Literal["amount_desc", "amount_asc", "date_desc", "date_asc"]

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
    group_by: GroupBy | None = Field(
        default=None,
        description="The dimension to split/compare totals by (breakdown & compare).",
    )
    sort: Sort | None = Field(
        default=None,
        description="Ordering for a `list`: by amount or date, ascending or descending.",
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Top-N cap for a `list` (e.g. 'the 3 biggest expenses' -> 3).",
    )
    compare_subjects: list[str] | None = Field(
        default=None,
        description=(
            "For a `compare`: the two-or-more things being weighed against each "
            "other, as their labels in `group_by` (e.g. ['Mom','Dad'] or "
            "['dining','fuel']). Empty/absent -> compare the top two automatically."
        ),
    )
    disputed: bool | None = Field(
        default=None,
        description=(
            "Filter by dispute status: true = only receipts a member flagged as "
            "disputed, false = only undisputed. Null = no dispute filter."
        ),
    )


class TripInfo(BaseModel):
    """Metadata about the container, so the ask can answer non-financial
    questions ("who's on this trip", "when was it", trip overview)."""

    name: str
    base_currency: str
    member_names: list[str] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    is_personal: bool = False


class AskPlanner(Protocol):
    def plan(self, question: str, context: "AskContext") -> QuerySpec: ...


class AskContext(BaseModel):
    today: date
    base_currency: str
    categories: list[str]
    people: list[str]
    # Recent Q&A turns (oldest first) so the planner can resolve a follow-up
    # against the prior question. Empty for a fresh, single-shot question.
    history: list[AskTurn] = Field(default_factory=list)


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
    if spec.disputed is not None:
        # A receipt is disputed iff a member flagged it (disputed_by_persona_id set).
        out = [r for r in out if bool(r.disputed_by_persona_id) == spec.disputed]
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
    if spec.disputed is True:
        bits.append("flagged as disputed")
    elif spec.disputed is False:
        bits.append("not disputed")
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


def _fmt_list(names: list[str]) -> str:
    names = [n for n in names if n]
    if not names:
        return "no one"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _answer_members(
    question: str, trip_info: TripInfo | None
) -> AskResponse:
    resp = dict(question=question, operation="members", value=None, currency=None)
    if trip_info is None or trip_info.is_personal:
        return AskResponse(
            **resp, answer="This is your personal ledger — just you.", matched=[]
        )
    people = trip_info.member_names
    return AskResponse(
        **{**resp, "value": float(len(people))},
        answer=(
            f"{len(people)} {'person is' if len(people) == 1 else 'people are'} on "
            f"{trip_info.name}: {_fmt_list(people)}."
        ),
        matched=[],
    )


def _answer_overview(
    question: str,
    receipts: list[Receipt],
    base_currency: str,
    trip_info: TripInfo | None,
) -> AskResponse:
    resp = dict(question=question, operation="overview", currency=base_currency)
    total = round(sum(r.base_amount for r in receipts if r.base_amount is not None), 2)
    n = len(receipts)
    nc = sum(1 for r in receipts if r.base_amount is None and r.total is not None)

    parts = []
    if trip_info and not trip_info.is_personal:
        parts.append(f"{trip_info.name}")
        if trip_info.start_date and trip_info.end_date:
            parts.append(f"{trip_info.start_date} to {trip_info.end_date}")
        parts.append(f"with {_fmt_list(trip_info.member_names)}")
    else:
        parts.append("Your personal ledger")

    body = ", ".join(parts)
    summary = (
        f"{body}. {n} receipt{'s' if n != 1 else ''}, "
        f"{_money(total, base_currency)} total"
    )
    if nc:
        summary += f" ({nc} not converted)"
    summary += "."
    return AskResponse(
        **{**resp, "value": total}, answer=summary, matched=receipts
    )


def _group_key(r: Receipt, group_by: GroupBy, personas: list[Persona]) -> str:
    """The human label a receipt is bucketed under for a breakdown."""
    if group_by == "category":
        return r.category.value if r.category else "uncategorized"
    if group_by == "paid_by":
        return _persona_name(r.paid_by_persona_id, personas) if r.paid_by_persona_id else "unknown"
    if group_by == "currency":
        return (r.currency or "?").upper()
    # merchant
    return r.merchant or "unknown"


def _answer_breakdown(
    question: str,
    spec: QuerySpec,
    receipts: list[Receipt],
    personas: list[Persona],
    base_currency: str,
) -> AskResponse:
    """Split a total across a dimension (per person / category / currency /
    merchant). Filters apply first, so 'break down dining by person' works."""
    group_by = spec.group_by or "category"
    matched = _filter(spec, receipts, personas)
    desc = _describe(spec, personas)
    resp = dict(question=question, operation="breakdown", currency=base_currency, value=None)

    # Accumulate summed base_amount and a receipt count per group. Rows without a
    # converted base_amount still count toward the group's tally but not its sum.
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for r in matched:
        key = _group_key(r, group_by, personas)
        counts[key] = counts.get(key, 0) + 1
        if r.base_amount is not None:
            sums[key] = sums.get(key, 0.0) + r.base_amount

    if not matched:
        return AskResponse(
            **{**resp, "value": 0.0},
            answer=f"No receipts to break down{desc}.",
            matched=[],
            breakdown=[],
        )

    grand = sum(sums.values())
    rows = [
        BreakdownRow(
            label=key,
            value=round(sums.get(key, 0.0), 2),
            currency=base_currency,
            count=counts[key],
            share=round(100.0 * sums.get(key, 0.0) / grand, 1) if grand else 0.0,
        )
        for key in counts
    ]
    # Largest spend first; ties broken by label for a stable, readable order.
    rows.sort(key=lambda row: (-row.value, row.label))

    total = round(sum(row.value for row in rows), 2)
    # (singular, plural) per dimension — irregular plurals ("people", "categories")
    # so the sentence reads naturally regardless of how many groups there are.
    singular, plural = {
        "paid_by": ("person", "people"),
        "category": ("category", "categories"),
        "currency": ("currency", "currencies"),
        "merchant": ("merchant", "merchants"),
    }[group_by]
    dim = singular if len(rows) == 1 else plural
    top = rows[0]
    # Naming the top group's share turns "what percent did Dad cover?" /
    # "what fraction was food?" into a directly answerable breakdown.
    pct = f" ({top.share:.0f}%)" if grand else ""
    answer = (
        f"{_money(total, base_currency)}{desc} across {len(rows)} {dim} — "
        f"{top.label} highest at {_money(top.value, base_currency)}{pct}."
    )
    return AskResponse(
        **{**resp, "value": total}, answer=answer, matched=matched, breakdown=rows
    )


def _sorted(receipts: list[Receipt], sort: Sort | None) -> list[Receipt]:
    """Order receipts for a `list`. Rows missing the sort key sink to the end so
    a top-N never surfaces blanks. Default (no sort) keeps insertion order."""
    if sort is None:
        return receipts
    if sort in ("amount_desc", "amount_asc"):
        keyed = [r for r in receipts if r.base_amount is not None]
        keyless = [r for r in receipts if r.base_amount is None]
        keyed.sort(key=lambda r: r.base_amount, reverse=(sort == "amount_desc"))
        return keyed + keyless
    keyed = [r for r in receipts if r.purchase_date is not None]
    keyless = [r for r in receipts if r.purchase_date is None]
    keyed.sort(key=lambda r: r.purchase_date, reverse=(sort == "date_desc"))
    return keyed + keyless


def _receipt_label(r: Receipt, base_currency: str) -> str:
    where = r.merchant or "a receipt"
    amt = _money(r.base_amount, base_currency) if r.base_amount is not None else "—"
    label = f"{where} {amt}"
    if r.disputed_by_persona_id:
        # Surface the flag (and the reason, if given) so a disputed-receipts list
        # is actually informative, not just names and amounts.
        label += f" (disputed: {r.dispute_reason})" if r.dispute_reason else " (disputed)"
    return label


def _answer_list(
    question: str,
    spec: QuerySpec,
    receipts: list[Receipt],
    personas: list[Persona],
    base_currency: str,
) -> AskResponse:
    """A `list` answer, now sortable and limitable so 'the 3 biggest expenses'
    and 'receipts from most to least expensive' return the right rows in the
    right order — and the sentence itemises the top few instead of just counting.
    """
    matched = _filter(spec, receipts, personas)
    matched = _sorted(matched, spec.sort)
    if spec.limit is not None:
        matched = matched[: spec.limit]
    desc = _describe(spec, personas)
    resp = dict(question=question, operation="list", currency=None, value=None)

    n = len(matched)
    if n == 0:
        return AskResponse(**resp, answer=f"No receipts found{desc}.", matched=[])

    # Itemise the leading rows (all of them when few, a preview when many) so the
    # sentence carries the amounts, not just a bare count.
    preview = matched[: min(n, spec.limit or 5)]
    items = "; ".join(_receipt_label(r, base_currency) for r in preview)
    head = f"{n} receipt{'s' if n != 1 else ''}{desc}"
    answer = f"{head}: {items}." if items else f"{head}."
    if n > len(preview):
        answer = f"{head} — top {len(preview)}: {items}."
    return AskResponse(**resp, answer=answer, matched=matched)


def _answer_compare(
    question: str,
    spec: QuerySpec,
    receipts: list[Receipt],
    personas: list[Persona],
    base_currency: str,
) -> AskResponse:
    """Weigh two (or more) subjects against each other in one dimension:
    "who spent more, Mom or Dad?", "more on dining or fuel?", "how much more did
    Mom pay than Dad?". `value` is the gap between the top two, so it's checkable.
    """
    group_by = spec.group_by or "paid_by"
    matched = _filter(spec, receipts, personas)
    resp = dict(question=question, operation="compare", currency=base_currency, value=None)

    sums: dict[str, float] = {}
    for r in matched:
        if r.base_amount is None:
            continue
        key = _group_key(r, group_by, personas)
        sums[key] = sums.get(key, 0.0) + r.base_amount

    # Resolve the requested subjects to their group labels. A named subject that
    # has no receipts is a real 0 (a member who paid nothing), not a miss.
    subjects = spec.compare_subjects or []
    resolved: list[tuple[str, float]] = []
    for raw in subjects:
        if group_by == "paid_by":
            pid = _resolve_persona(raw, personas)
            label = _persona_name(pid, personas) if pid else raw
        else:
            label = raw
        # case-insensitive match against the labels actually present
        hit = next((k for k in sums if k.lower() == label.lower()), None)
        resolved.append((hit or label, sums.get(hit, 0.0) if hit else 0.0))

    if len(resolved) < 2:
        # No explicit pair -> compare the two biggest groups in the dimension.
        resolved = sorted(sums.items(), key=lambda kv: -kv[1])[:2]

    if len(resolved) < 2:
        return AskResponse(
            **resp, answer="I need two things to compare — try 'Mom vs Dad' or "
            "'dining vs fuel'.", matched=[],
        )

    resolved.sort(key=lambda kv: -kv[1])
    (top_label, top_val), (next_label, next_val) = resolved[0], resolved[1]
    gap = round(top_val - next_val, 2)
    # Only the receipts belonging to the compared subjects are the evidence.
    names = {lbl.lower() for lbl, _ in resolved}
    evidence = [r for r in matched if _group_key(r, group_by, personas).lower() in names]

    parts = ", ".join(
        f"{lbl} {_money(round(val, 2), base_currency)}" for lbl, val in resolved
    )
    if gap < 0.01:
        answer = f"It's a tie — {parts}."
        gap = 0.0
    else:
        answer = (
            f"{top_label} spent more — {parts} "
            f"({_money(gap, base_currency)} more)."
        )
    return AskResponse(**{**resp, "value": gap}, answer=answer, matched=evidence)


def _answer_unsupported(question: str) -> AskResponse:
    """Honest refusal (golden rule 6): the question is out of scope for a receipt
    ledger — don't map it to an arbitrary number and pretend we understood."""
    return AskResponse(
        question=question,
        operation="unsupported",
        value=None,
        answer=(
            "I can only answer questions about the receipts on this ledger — "
            "totals, who paid, categories, dates, and settle-up. Try rephrasing "
            "around your spending."
        ),
        matched=[],
    )


def run_query(
    question: str,
    spec: QuerySpec,
    receipts: list[Receipt],
    personas: list[Persona],
    base_currency: str,
    member_ids: list[str] | None = None,
    trip_info: TripInfo | None = None,
) -> AskResponse:
    if spec.operation == "members":
        return _answer_members(question, trip_info)
    if spec.operation == "overview":
        return _answer_overview(question, receipts, base_currency, trip_info)
    if spec.operation == "balance":
        return _answer_balance(
            question, spec, receipts, personas, base_currency, member_ids
        )
    if spec.operation == "breakdown":
        return _answer_breakdown(question, spec, receipts, personas, base_currency)
    if spec.operation == "compare":
        return _answer_compare(question, spec, receipts, personas, base_currency)
    if spec.operation == "list":
        return _answer_list(question, spec, receipts, personas, base_currency)
    if spec.operation == "unsupported":
        return _answer_unsupported(question)

    matched = _filter(spec, receipts, personas)
    amounts = [r.base_amount for r in matched if r.base_amount is not None]
    desc = _describe(spec, personas)
    n = len(matched)
    resp = dict(question=question, operation=spec.operation, currency=None, value=None)

    if n == 0:
        # Zero matches is a *valid, answerable* result for sum/count — e.g. a real
        # trip member who paid for nothing paid exactly 0 — not a failure to
        # understand. Only average/max/min have no meaningful zero.
        if spec.operation == "sum":
            return AskResponse(
                **{**resp, "value": 0.0, "currency": base_currency},
                answer=f"{_money(0.0, base_currency)}{desc} — nothing recorded.",
                matched=[],
            )
        if spec.operation == "count":
            return AskResponse(
                **{**resp, "value": 0.0}, answer=f"0 receipts{desc}.", matched=[]
            )
        return AskResponse(**resp, answer=f"No receipts found{desc}.", matched=[])

    if spec.operation == "count":
        answer = f"{n} receipt{'s' if n != 1 else ''}{desc}."
        return AskResponse(**{**resp, "value": float(n)}, answer=answer, matched=matched)

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
    max      -> "biggest / most expensive" (the SINGLE top one)
    min      -> "cheapest / smallest" (the SINGLE lowest one)
    list     -> "show me / which". Also for TOP-N and sorted lists: "the 3
                biggest expenses", "receipts from most to least expensive",
                "our smallest purchases". Set sort and limit (see below).
    balance  -> settle-up: "how much is owed to X", "how much does X owe", "is X settled up"
    members  -> who is on the trip: "who was involved", "who's on this trip", "who are the members"
    overview -> details of THIS TRIP: "tell me about this trip", "trip summary",
                "when was THIS TRIP", "give me an overview". NOT the current
                date/time — "what day is it today" is unsupported, not overview.
    breakdown-> split a total across a dimension: "how much did EACH person spend",
                "spending BY category", "break it down by merchant", "per-person totals",
                "which category costs the most", "what PERCENT/FRACTION did X cover".
                Set group_by (see below). Prefer this over sum/list whenever the
                question asks for a per-group split or a share/percentage.
    compare  -> weigh TWO (or more) named things against each other: "did we
                spend more on dining OR fuel?", "who spent more, Mom or Dad?",
                "how much MORE did Mom pay than Dad?". Set group_by to the
                dimension and compare_subjects to the named things (see below).
    unsupported-> the question is NOT about this ledger's receipts/spending:
                weather, advice, opinions, the future, general chit-chat, math,
                trivia, or the CURRENT date/day/time ("what day is it today",
                "what's the date"). When in doubt, if the question can't be
                answered from the trip's receipts, choose unsupported — do NOT
                force a number or a trip summary onto it.
- For a "what PERCENT / SHARE / FRACTION did X ..." question, use breakdown over
  the WHOLE dimension and do NOT also set the matching filter to X — the split
  already contains X's row and its share, and filtering to X would drop the
  denominator (you'd get X's own total, not X's share). e.g. "what percent did
  Mom pay?" -> breakdown, group_by=paid_by, paid_by=null (NOT paid_by=Mom).
- For breakdown AND compare, set group_by to the dimension:
    category | paid_by | currency | merchant.
  ("by category"->category, "each/per person"/"by who paid"->paid_by,
   "by currency"->currency, "by store/merchant/vendor"->merchant.)
  Filters still apply: "break down DINING by person" -> operation=breakdown,
  group_by=paid_by, category=dining. Leave group_by null for sum/count/list/etc.
- For compare, also set compare_subjects to the labels being weighed, matching
  group_by: people names for paid_by ("Mom or Dad" -> ["Mom","Dad"]), category
  values for category ("dining vs fuel" -> ["dining","fuel"]). Leave it null only
  if the question says "compare everyone/each" without naming which two.
- For a top-N or sorted list, set:
    sort: amount_desc ("biggest/most expensive/highest"), amount_asc
          ("cheapest/smallest/lowest"), date_desc ("latest/most recent"),
          date_asc ("earliest/oldest").
    limit: the N in "top N / N biggest" (e.g. 3). Leave null if no count is given.
  Leave sort and limit null for every non-list operation.
- For a balance question, set paid_by to the person the question is about.
- Only set category to one of the listed categories, else leave null.
- Whenever the question is about what a specific person paid, owes, or spent
  ("how much did Bob pay", "Bob's total"), set paid_by to that person's name if
  it matches one of the listed people. Set it even if that person may have spent
  nothing. Only leave paid_by null when the question is about the whole group
  ("how much did we spend", "the total").
- currency: an ISO code (e.g. USD, EUR) if the question is about expenses in a
  specific currency ("in dollars", "any USD expenses"), else null.
- Resolve relative dates ("last month", "in June", "this week") to date_from/date_to
  using today's date. Leave both null if no time filter.
- merchant_contains: a store/vendor name if the question names one, else null.
- disputed: set true for questions about DISPUTED / flagged / contested /
  challenged / questioned receipts ("which receipts are disputed?", "any
  disputes?", "what did we flag?", "how much is disputed?"); set false for
  explicitly undisputed ("which aren't disputed"); else null. Combine with the
  operation as usual: "which receipts are disputed" -> list+disputed=true,
  "how many disputes" -> count+disputed=true, "how much is disputed" ->
  sum+disputed=true.
- FOLLOW-UPS: if a "Recent conversation" block is shown below and the CURRENT
  question is a fragment that refers back to it ("and on dining?", "what about
  Bob?", "just in June", "by category instead", "only USD ones"), resolve it into
  a COMPLETE spec: start from the most recent question's filters, keep the ones
  still relevant, and apply the change the new question asks for. If the current
  question stands on its own, ignore the conversation entirely.

Examples (question -> spec):
- "how much did we spend?" -> {{"operation": "sum"}}
- "how much did each of us spend?" -> {{"operation": "breakdown", "group_by": "paid_by"}}
- "what did we spend by category?" -> {{"operation": "breakdown", "group_by": "category"}}
- "what percent did Mom pay?" -> {{"operation": "breakdown", "group_by": "paid_by"}}
- "break down dining per person" -> {{"operation": "breakdown", "group_by": "paid_by", "category": "dining"}}
- "which store did we spend the most at?" -> {{"operation": "breakdown", "group_by": "merchant"}}
- "did we spend more on dining or fuel?" -> {{"operation": "compare", "group_by": "category", "compare_subjects": ["dining", "fuel"]}}
- "who spent more, Mom or Dad?" -> {{"operation": "compare", "group_by": "paid_by", "compare_subjects": ["Mom", "Dad"]}}
- "how much more did Mom pay than Dad?" -> {{"operation": "compare", "group_by": "paid_by", "compare_subjects": ["Mom", "Dad"]}}
- "the 3 biggest expenses" -> {{"operation": "list", "sort": "amount_desc", "limit": 3}}
- "receipts from most to least expensive" -> {{"operation": "list", "sort": "amount_desc"}}
- "how much did Dad spend?" -> {{"operation": "sum", "paid_by": "Dad"}}
- "show me the fuel receipts" -> {{"operation": "list", "category": "fuel"}}
- "which receipts are disputed?" -> {{"operation": "list", "disputed": true}}
- "how many disputes are there?" -> {{"operation": "count", "disputed": true}}
- "what's the weather in Goa?" -> {{"operation": "unsupported"}}
- "what day is it today?" -> {{"operation": "unsupported"}}

Return ONLY the JSON."""


def _history_block(history: list[AskTurn], limit: int = 6) -> str:
    """Render the most recent turns for the planner. Bounded to the last few so
    a long thread doesn't blow up the prompt; oldest-first for natural reading."""
    if not history:
        return ""
    recent = history[-limit:]
    lines = "\n".join(f"Q: {t.question}\nA: {t.answer}" for t in recent)
    return (
        "\n\nRecent conversation (oldest first — use only to resolve a follow-up):"
        f"\n{lines}"
    )


def build_planner_prompt(context: AskContext) -> str:
    """The full system prompt for a plan() call, including any conversation
    history. Pulled out as a pure function so it's testable without Gemini."""
    prompt = PLANNER_PROMPT.format(
        today=context.today.isoformat(),
        base_currency=context.base_currency,
        categories=", ".join(context.categories),
        people=", ".join(context.people) or "(none)",
    )
    return prompt + _history_block(context.history)


class GeminiPlanner:
    """Live planner using Gemini structured output."""

    def plan(self, question: str, context: AskContext) -> QuerySpec:
        from google import genai
        from google.genai import types

        from .config import get_settings

        settings = get_settings()
        client = genai.Client(api_key=settings.gemini_api_key)
        model = settings.gemini_ask_model or settings.gemini_model
        prompt = build_planner_prompt(context)
        resp = client.models.generate_content(
            model=model,
            contents=[prompt, f"Current question: {question}"],
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
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
        answer = (
            "The assistant has hit its free-tier usage limit for now. "
            "Please try again a little later."
        )
    else:
        answer = "Sorry, I couldn't process that question just now. Try rephrasing it."
    return AskResponse(
        question=question, operation="unavailable", value=None, answer=answer, matched=[]
    )
