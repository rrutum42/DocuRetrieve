"""Labeled dataset for the natural-language ask eval.

A fixed synthetic trip ledger + a set of questions, each labeled with the
CORRECT structured query (hand_spec) and the expected answer. Two things get
measured from this:

  * the executor (run_query) — does the right QuerySpec produce the right answer?
    Deterministic, gated in CI (tests/test_ask_eval.py).
  * the planner (Gemini) — does a natural-language question map to the right
    QuerySpec? Needs live calls; run via `python -m evals.ask_eval`.

Everything here is synthetic (Mom/Dad/Kid, invented receipts), so unlike the
extraction eval this dataset and its results are fully committable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.api_models import Persona, Receipt
from app.ask import QuerySpec, TripInfo

# --- fixture ledger ---------------------------------------------------------

MOM = Persona(id="m", name="Mom")
DAD = Persona(id="d", name="Dad")
KID = Persona(id="k", name="Kid")
STRANGER = Persona(id="s", name="Stranger")  # exists, but NOT on the trip
PERSONAS = [MOM, DAD, KID, STRANGER]
MEMBER_IDS = ["m", "d", "k"]
BASE = "INR"

TRIP_INFO = TripInfo(
    name="Goa 2026",
    base_currency=BASE,
    member_names=["Mom", "Dad", "Kid"],
    start_date=date(2026, 6, 1),
    end_date=date(2026, 7, 15),
)


def _r(rid, payer, cat, merch, day, base_amount, currency="INR"):
    return Receipt(
        id=rid,
        owner_persona_id="m",
        paid_by_persona_id=payer,
        merchant=merch,
        purchase_date=day,
        currency=currency,
        total=base_amount if currency == "INR" else None,
        category=cat,
        base_currency=BASE,
        base_amount=base_amount,
    )


RECEIPTS = [
    _r("r1", "m", "dining", "Bistro", date(2026, 6, 5), 100.0),
    _r("r2", "m", "groceries", "BigBasket", date(2026, 6, 12), 200.0),
    _r("r3", "d", "dining", "Cafe", date(2026, 7, 1), 50.0),
    _r("r4", "d", "fuel", "Shell", date(2026, 6, 20), 300.0),
    _r("r5", "m", "dining", "Bistro", date(2026, 7, 10), 150.0, currency="USD"),
]
# total 800 | Mom paid 450, Dad 350, Kid 0 | fair share 800/3 = 266.67
# dining 300 (x3), groceries 200, fuel 300 | June 600, July 200 | USD receipts: 1


@dataclass
class AskCase:
    question: str
    hand_spec: QuerySpec           # the correct compiled query (executor gate)
    op: str                        # expected operation
    value: float | None = None     # expected numeric answer (None = don't check)
    matched: int | None = None     # expected matched-receipt count (None = skip)
    note: str = ""


CASES: list[AskCase] = [
    AskCase("How much did we spend in total?", QuerySpec(operation="sum"), "sum", 800.0),
    AskCase("How much did we spend on dining?",
            QuerySpec(operation="sum", category="dining"), "sum", 300.0, matched=3),
    AskCase("How many receipts are there?", QuerySpec(operation="count"), "count", 5.0),
    AskCase("How much did Dad pay?",
            QuerySpec(operation="sum", paid_by="Dad"), "sum", 350.0),
    AskCase("How much did Kid pay?",
            QuerySpec(operation="sum", paid_by="Kid"), "sum", 0.0,
            note="member who paid nothing -> 0, not 'not found'"),
    AskCase("What was the most expensive purchase?",
            QuerySpec(operation="max"), "max", 300.0),
    AskCase("How much did we spend in June?",
            QuerySpec(operation="sum", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)),
            "sum", 600.0),
    AskCase("How much is owed to Mom?",
            QuerySpec(operation="balance", paid_by="Mom"), "balance", 183.33,
            note="settle-up: paid 450 - fair share 266.67"),
    AskCase("How much does Kid owe?",
            QuerySpec(operation="balance", paid_by="Kid"), "balance", -266.67),
    AskCase("Who is on this trip?", QuerySpec(operation="members"), "members", 3.0),
    AskCase("Give me an overview of this trip.",
            QuerySpec(operation="overview"), "overview", 800.0),
    AskCase("How many expenses were in USD?",
            QuerySpec(operation="count", currency="USD"), "count", 1.0,
            note="native-currency filter"),
    AskCase("How much did Stranger pay?",
            QuerySpec(operation="sum", paid_by="Stranger"), "sum", 0.0,
            note="non-member payer -> 0, must NOT sum whole trip"),
    AskCase("How much did we spend on groceries?",
            QuerySpec(operation="sum", category="groceries"), "sum", 200.0),
    AskCase("Show me the dining receipts.",
            QuerySpec(operation="list", category="dining"), "list", matched=3),
    AskCase("How much did each person spend?",
            QuerySpec(operation="breakdown", group_by="paid_by"),
            "breakdown", 800.0, matched=5,
            note="per-person split; rows sum to the grand total"),
    AskCase("What did we spend by category?",
            QuerySpec(operation="breakdown", group_by="category"),
            "breakdown", 800.0, matched=5),
    AskCase("Break down dining by person.",
            QuerySpec(operation="breakdown", group_by="paid_by", category="dining"),
            "breakdown", 300.0, matched=3,
            note="breakdown composed with a category filter"),
    # --- comparison: weigh two named subjects (used to collapse to a breakdown) -
    AskCase("Who spent more, Mom or Dad?",
            QuerySpec(operation="compare", group_by="paid_by",
                      compare_subjects=["Mom", "Dad"]),
            "compare", 100.0, matched=5,
            note="Mom 450 vs Dad 350 -> gap 100; must not include Kid"),
    AskCase("How much more did Mom pay than Dad?",
            QuerySpec(operation="compare", group_by="paid_by",
                      compare_subjects=["Mom", "Dad"]),
            "compare", 100.0, matched=5,
            note="'how much more' phrasing -> the gap, 100"),
    AskCase("Did we spend more on dining or fuel?",
            QuerySpec(operation="compare", group_by="category",
                      compare_subjects=["dining", "fuel"]),
            "compare", 0.0, matched=4,
            note="dining 300 vs fuel 300 -> a tie (gap 0)"),
    # --- top-N / sorted list (max used to return only one) ----------------------
    AskCase("What are the 3 biggest expenses?",
            QuerySpec(operation="list", sort="amount_desc", limit=3),
            "list", matched=3,
            note="top-N: three rows, largest first (300, 200, 150)"),
    AskCase("List receipts from most to least expensive.",
            QuerySpec(operation="list", sort="amount_desc"),
            "list", matched=5, note="sorted list, no limit"),
    # --- share / percentage (answered as a breakdown) ---------------------------
    AskCase("What percent did Mom pay?",
            QuerySpec(operation="breakdown", group_by="paid_by"),
            "breakdown", 800.0, matched=5,
            note="answered by a per-person breakdown carrying each row's share"),
    # --- out of scope: honest refusal, not a fabricated number ------------------
    AskCase("What's the weather in Goa?",
            QuerySpec(operation="unsupported"),
            "unsupported", None, matched=0,
            note="off-ledger question -> unsupported, never a made-up total"),
    AskCase("What day is it today?",
            QuerySpec(operation="unsupported"),
            "unsupported", None, matched=0,
            note="current-date question must NOT be mistaken for the trip's dates "
                 "(overview) — regression from a real live miss"),
    # --- disputes: filter by a member-flagged receipt ---------------------------
    AskCase("Are any receipts disputed?",
            QuerySpec(operation="count", disputed=True),
            "count", 0.0, matched=0,
            note="dispute filter; this fixture has none -> honest 0"),
]
