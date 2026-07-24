"""Natural-language ask tests.

The query executor (run_query) is pure and gets the bulk of the coverage. One
endpoint test exercises the wiring with a stubbed planner (no Gemini).
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api_models import AskTurn, Persona, Receipt
from app.ask import AskContext, AskPlanner, QuerySpec, TripInfo, build_planner_prompt, run_query
from app.deps import get_ask_planner, get_fx, get_repository, get_storage
from app.main import app
from app.repository import InMemoryRepository
from app.storage import NoopStorage
from tests.test_receipts import FakeFx

MOM = Persona(id="mom", name="Mom")
DAD = Persona(id="dad", name="Dad")
PEOPLE = [MOM, DAD]


def rcpt(
    paid_by, base_amount, *, category="dining", merchant="Cafe", day="2026-06-10", currency="INR"
):
    return Receipt(
        id=str(uuid.uuid4()),
        owner_persona_id="mom",
        paid_by_persona_id=paid_by,
        merchant=merchant,
        purchase_date=day,
        currency=currency,
        total=base_amount,
        category=category,
        base_currency="INR",
        base_amount=base_amount,
    )


RECEIPTS = [
    rcpt("mom", 100.0, category="dining", merchant="Bistro", day="2026-06-05"),
    rcpt("mom", 200.0, category="groceries", merchant="Whole Foods", day="2026-06-12"),
    rcpt("dad", 50.0, category="dining", merchant="Bistro", day="2026-07-01"),
]


def test_sum_all():
    r = run_query("total?", QuerySpec(operation="sum"), RECEIPTS, PEOPLE, "INR")
    assert r.value == 350.0 and r.currency == "INR"


def test_sum_filtered_by_category():
    r = run_query(
        "dining total", QuerySpec(operation="sum", category="dining"), RECEIPTS, PEOPLE, "INR"
    )
    assert r.value == 150.0
    assert len(r.matched) == 2


def test_sum_filtered_by_payer_name():
    r = run_query(
        "how much did dad pay",
        QuerySpec(operation="sum", paid_by="Dad"),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    assert r.value == 50.0


def test_count_operation():
    r = run_query("how many", QuerySpec(operation="count"), RECEIPTS, PEOPLE, "INR")
    assert r.value == 3.0 and r.currency is None


def test_max_returns_single_receipt():
    r = run_query("biggest", QuerySpec(operation="max"), RECEIPTS, PEOPLE, "INR")
    assert r.value == 200.0
    assert len(r.matched) == 1 and r.matched[0].merchant == "Whole Foods"


def test_date_range_filter():
    r = run_query(
        "spend in June",
        QuerySpec(operation="sum", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    assert r.value == 300.0  # excludes the July receipt


def test_merchant_filter():
    r = run_query(
        "spend at Bistro",
        QuerySpec(operation="sum", merchant_contains="bistro"),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    assert r.value == 150.0


def test_sum_for_payer_with_zero_expenses_is_zero_not_unanswered():
    # Dad is a real person, but here he paid for nothing -> the answer is 0, not
    # "no receipts found".
    only_mom = [rcpt("mom", 100.0), rcpt("mom", 50.0)]
    r = run_query(
        "how much did Dad pay?",
        QuerySpec(operation="sum", paid_by="Dad"),
        only_mom,
        PEOPLE,
        "INR",
    )
    assert r.value == 0.0
    assert r.currency == "INR"
    assert "Dad" in r.answer


def test_count_for_payer_with_zero_expenses_is_zero():
    only_mom = [rcpt("mom", 100.0)]
    r = run_query(
        "how many did Dad pay for?",
        QuerySpec(operation="count", paid_by="Dad"),
        only_mom,
        PEOPLE,
        "INR",
    )
    assert r.value == 0.0
    assert "0 receipts" in r.answer


def test_average_with_no_match_still_says_none():
    # average has no meaningful zero -> stays "no receipts found"
    r = run_query(
        "avg fuel", QuerySpec(operation="average", category="fuel"), RECEIPTS, PEOPLE, "INR"
    )
    assert r.value is None
    assert "No receipts" in r.answer


def test_unknown_payer_yields_no_matches():
    r = run_query(
        "what did Zoe pay",
        QuerySpec(operation="sum", paid_by="Zoe"),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    assert r.matched == []


def test_currency_filter():
    mixed = [
        rcpt("mom", 100.0, currency="INR"),
        rcpt("dad", 40.0, currency="USD", merchant="US Diner"),
    ]
    r = run_query(
        "any expenses in USD?",
        QuerySpec(operation="count", currency="usd"),
        mixed,
        PEOPLE,
        "INR",
    )
    assert r.value == 1.0
    assert r.matched[0].merchant == "US Diner"


# --- disputed filter --------------------------------------------------------

def _disputed(r, reason="looks fake"):
    return r.model_copy(update={"disputed_by_persona_id": "mom", "dispute_reason": reason})


DISPUTE_SET = [
    _disputed(rcpt("mom", 100.0, merchant="Sketchy Bar"), reason="never went here"),
    rcpt("dad", 50.0, merchant="Cafe"),
    rcpt("mom", 200.0, merchant="BigBasket"),
]


def test_list_disputed_only():
    r = run_query(
        "which receipts are disputed?",
        QuerySpec(operation="list", disputed=True),
        DISPUTE_SET, PEOPLE, "INR",
    )
    assert len(r.matched) == 1 and r.matched[0].merchant == "Sketchy Bar"
    assert "disputed" in r.answer.lower()
    assert "never went here" in r.answer  # reason surfaced in the itemization


def test_count_disputed():
    r = run_query(
        "how many disputes?",
        QuerySpec(operation="count", disputed=True),
        DISPUTE_SET, PEOPLE, "INR",
    )
    assert r.value == 1.0


def test_sum_disputed_amount():
    r = run_query(
        "how much is disputed?",
        QuerySpec(operation="sum", disputed=True),
        DISPUTE_SET, PEOPLE, "INR",
    )
    assert r.value == 100.0


def test_filter_undisputed_excludes_flagged():
    r = run_query(
        "undisputed total",
        QuerySpec(operation="sum", disputed=False),
        DISPUTE_SET, PEOPLE, "INR",
    )
    assert r.value == 250.0  # 50 + 200, the disputed 100 excluded
    assert len(r.matched) == 2


def test_count_disputed_when_none_is_zero():
    # RECEIPTS has no disputes -> an honest 0, not a failure
    r = run_query(
        "any disputes?",
        QuerySpec(operation="count", disputed=True),
        RECEIPTS, PEOPLE, "INR",
    )
    assert r.value == 0.0


# --- breakdown (group_by) ---------------------------------------------------

def test_breakdown_by_category_sums_each_group():
    r = run_query(
        "spend by category",
        QuerySpec(operation="breakdown", group_by="category"),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    rows = {row.label: row for row in r.breakdown}
    assert rows["dining"].value == 150.0 and rows["dining"].count == 2
    assert rows["groceries"].value == 200.0 and rows["groceries"].count == 1
    assert r.value == 350.0                 # rows sum to the grand total
    assert len(r.matched) == 3              # all receipts remain traceable
    # sorted largest-first
    assert r.breakdown[0].label == "groceries"


def test_breakdown_by_person_uses_names():
    r = run_query(
        "how much did each of us spend",
        QuerySpec(operation="breakdown", group_by="paid_by"),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    rows = {row.label: row.value for row in r.breakdown}
    assert rows == {"Mom": 300.0, "Dad": 50.0}
    assert "Mom" in r.answer  # top spender named in the sentence


def test_breakdown_respects_filters():
    # break down dining by person -> only the two dining receipts
    r = run_query(
        "break down dining by person",
        QuerySpec(operation="breakdown", group_by="paid_by", category="dining"),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    rows = {row.label: row.value for row in r.breakdown}
    assert rows == {"Mom": 100.0, "Dad": 50.0}
    assert len(r.matched) == 2


def test_breakdown_defaults_group_by_to_category():
    r = run_query(
        "break it down", QuerySpec(operation="breakdown"), RECEIPTS, PEOPLE, "INR"
    )
    assert {row.label for row in r.breakdown} == {"dining", "groceries"}


def test_breakdown_with_no_receipts_is_empty_not_crash():
    r = run_query(
        "spend by category",
        QuerySpec(operation="breakdown", group_by="category", category="fuel"),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    assert r.breakdown == []
    assert r.value == 0.0
    assert "No receipts" in r.answer


def test_breakdown_answer_pluralizes_dimension_correctly():
    # regression: "across 3 categorys"/"2 persons" -> "categories"/"people"
    by_cat = run_query(
        "by category", QuerySpec(operation="breakdown", group_by="category"),
        RECEIPTS, PEOPLE, "INR",
    )
    assert "categories" in by_cat.answer and "categorys" not in by_cat.answer
    by_person = run_query(
        "by person", QuerySpec(operation="breakdown", group_by="paid_by"),
        RECEIPTS, PEOPLE, "INR",
    )
    assert "people" in by_person.answer and "persons" not in by_person.answer


def test_breakdown_rows_carry_percent_share():
    r = run_query(
        "spend by category",
        QuerySpec(operation="breakdown", group_by="category"),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    rows = {row.label: row for row in r.breakdown}
    # groceries 200 / 350 total = 57.1%, dining 150 / 350 = 42.9%
    assert rows["groceries"].share == 57.1
    assert rows["dining"].share == 42.9
    assert "%" in r.answer  # top group's share is surfaced in the sentence


# --- list: sort + limit (top-N) ---------------------------------------------

def test_list_sorted_amount_desc_orders_and_itemizes():
    r = run_query(
        "receipts most to least expensive",
        QuerySpec(operation="list", sort="amount_desc"),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    amounts = [m.base_amount for m in r.matched]
    assert amounts == [200.0, 100.0, 50.0]  # descending
    assert "Whole Foods" in r.answer  # itemized, not just a count


def test_list_top_n_limits_matched_rows():
    r = run_query(
        "the 2 biggest expenses",
        QuerySpec(operation="list", sort="amount_desc", limit=2),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    assert len(r.matched) == 2
    assert [m.base_amount for m in r.matched] == [200.0, 100.0]


def test_list_sort_ascending_for_cheapest():
    r = run_query(
        "our cheapest purchase",
        QuerySpec(operation="list", sort="amount_asc", limit=1),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    assert len(r.matched) == 1 and r.matched[0].base_amount == 50.0


def test_list_empty_is_honest():
    r = run_query(
        "show fuel receipts",
        QuerySpec(operation="list", category="fuel"),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    assert r.matched == [] and "No receipts" in r.answer


# --- compare operation ------------------------------------------------------

def test_compare_two_people_reports_gap_and_leader():
    # Mom paid 300, Dad 50 -> Mom leads by 250
    r = run_query(
        "who spent more, Mom or Dad?",
        QuerySpec(operation="compare", group_by="paid_by", compare_subjects=["Mom", "Dad"]),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    assert r.operation == "compare"
    assert r.value == 250.0
    assert "Mom spent more" in r.answer
    assert len(r.matched) == 3  # all three receipts belong to Mom or Dad


def test_compare_two_categories():
    r = run_query(
        "more on dining or groceries?",
        QuerySpec(
            operation="compare", group_by="category",
            compare_subjects=["dining", "groceries"],
        ),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    # dining 150 vs groceries 200 -> groceries leads by 50
    assert r.value == 50.0
    assert "groceries" in r.answer.lower()


def test_compare_subject_with_no_receipts_counts_as_zero():
    # Compare Dad (50) with a real member who paid nothing here.
    only_dad = [rcpt("dad", 50.0)]
    r = run_query(
        "who spent more, Mom or Dad?",
        QuerySpec(operation="compare", group_by="paid_by", compare_subjects=["Mom", "Dad"]),
        only_dad,
        PEOPLE,
        "INR",
    )
    assert r.value == 50.0  # Dad 50 - Mom 0
    assert "Dad spent more" in r.answer


def test_compare_without_subjects_uses_top_two():
    r = run_query(
        "compare our spenders",
        QuerySpec(operation="compare", group_by="paid_by"),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    assert r.value == 250.0  # Mom 300 vs Dad 50


def test_compare_tie():
    even = [rcpt("mom", 100.0), rcpt("dad", 100.0)]
    r = run_query(
        "who spent more?",
        QuerySpec(operation="compare", group_by="paid_by", compare_subjects=["Mom", "Dad"]),
        even,
        PEOPLE,
        "INR",
    )
    assert r.value == 0.0 and "tie" in r.answer.lower()


# --- unsupported (honest refusal) -------------------------------------------

def test_unsupported_question_is_refused_not_faked():
    r = run_query(
        "what's the weather like?",
        QuerySpec(operation="unsupported"),
        RECEIPTS,
        PEOPLE,
        "INR",
    )
    assert r.operation == "unsupported"
    assert r.value is None
    assert r.matched == []
    assert "receipts" in r.answer.lower()


# --- settle-up (balance operation) ------------------------------------------

MEMBERS = ["mom", "dad"]


def test_balance_person_is_owed():
    # mom paid 300, dad paid 50, total 350, fair share 175 -> mom owed 125
    r = run_query(
        "how much is owed to Mom",
        QuerySpec(operation="balance", paid_by="Mom"),
        RECEIPTS,
        PEOPLE,
        "INR",
        member_ids=MEMBERS,
    )
    assert r.value == 125.0
    assert "is owed" in r.answer


def test_balance_person_owes():
    r = run_query(
        "how much does Dad owe",
        QuerySpec(operation="balance", paid_by="Dad"),
        RECEIPTS,
        PEOPLE,
        "INR",
        member_ids=MEMBERS,
    )
    assert r.value == -125.0
    assert "owes" in r.answer


def test_balance_without_trip_is_explained():
    r = run_query(
        "how much is owed to Mom",
        QuerySpec(operation="balance", paid_by="Mom"),
        RECEIPTS,
        PEOPLE,
        "INR",
        member_ids=None,  # personal ledger
    )
    assert r.value is None
    assert "trip" in r.answer.lower()


def test_balance_unknown_person():
    r = run_query(
        "how much is owed to Zoe",
        QuerySpec(operation="balance", paid_by="Zoe"),
        RECEIPTS,
        PEOPLE,
        "INR",
        member_ids=MEMBERS,
    )
    assert "isn't on this trip" in r.answer


# --- endpoint wiring (stubbed planner, no Gemini) ---------------------------

class StubPlanner:
    def __init__(self, spec):
        self.spec = spec

    def plan(self, question, context):
        return self.spec


@pytest.fixture
def client():
    repo = InMemoryRepository()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_storage] = lambda: NoopStorage()
    app.dependency_overrides[get_fx] = lambda: FakeFx(rate=1.0)
    app.dependency_overrides[get_ask_planner] = lambda: StubPlanner(
        QuerySpec(operation="sum", category="dining")
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_ask_endpoint_end_to_end(client):
    mom = client.post("/api/personas", json={"name": "Mom"}).json()
    h = {"X-Persona-Id": mom["id"]}
    trip = client.post(
        "/api/trips", json={"name": "Trip", "base_currency": "INR"}, headers=h
    ).json()
    for amt, cat in [(100, "dining"), (200, "groceries"), (50, "dining")]:
        client.post(
            "/api/receipts",
            data={
                "payload": json.dumps(
                    {"trip_id": trip["id"], "currency": "INR", "total": amt, "category": cat}
                )
            },
            files={"file": ("r.jpg", io.BytesIO(b"x"), "image/jpeg")},
            headers=h,
        )
    # planner is stubbed to sum dining -> 150
    r = client.post(
        f"/api/trips/{trip['id']}/ask",
        json={"question": "how much on dining?"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["value"] == 150.0
    assert body["currency"] == "INR"
    assert len(body["matched"]) == 2


def test_members_lists_trip_people():
    info = TripInfo(name="France 2026", base_currency="INR", member_names=["Mom", "Dad", "Kid"])
    r = run_query(
        "who was involved?",
        QuerySpec(operation="members"),
        RECEIPTS,
        PEOPLE,
        "INR",
        trip_info=info,
    )
    assert r.value == 3.0
    assert "France 2026" in r.answer
    assert "Mom, Dad, and Kid" in r.answer


def test_members_on_personal_ledger():
    info = TripInfo(name="My Everyday", base_currency="INR", member_names=["Mom"], is_personal=True)
    r = run_query(
        "who's on this?", QuerySpec(operation="members"), RECEIPTS, PEOPLE, "INR", trip_info=info
    )
    assert "personal ledger" in r.answer.lower()


def test_overview_reports_metadata_and_totals():
    from datetime import date as _d

    info = TripInfo(
        name="France 2026",
        base_currency="INR",
        member_names=["Mom", "Dad"],
        start_date=_d(2026, 6, 1),
        end_date=_d(2026, 6, 10),
    )
    r = run_query(
        "tell me about this trip",
        QuerySpec(operation="overview"),
        RECEIPTS,
        PEOPLE,
        "INR",
        trip_info=info,
    )
    assert "France 2026" in r.answer
    assert "2026-06-01 to 2026-06-10" in r.answer
    assert "Mom and Dad" in r.answer
    assert "3 receipts" in r.answer      # RECEIPTS has 3
    assert r.value == 350.0              # 100 + 200 + 50
    assert len(r.matched) == 3           # overview returns the full breakdown


class RecordingPlanner:
    """Captures the AskContext it was given, returns a fixed spec."""

    def __init__(self, spec):
        self.spec = spec
        self.seen_context = None

    def plan(self, question, context):
        self.seen_context = context
        return self.spec


def test_ask_exposes_non_members_to_planner():
    """Regression: a question about a persona who isn't on the trip must still be
    bindable, else the payer filter drops and a payer question becomes a whole-
    trip sum. So the planner must see ALL persona names, not just members."""
    repo = InMemoryRepository()
    recorder = RecordingPlanner(QuerySpec(operation="sum", paid_by="Bob"))
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_storage] = lambda: NoopStorage()
    app.dependency_overrides[get_fx] = lambda: FakeFx(rate=1.0)
    app.dependency_overrides[get_ask_planner] = lambda: recorder
    try:
        c = TestClient(app)
        mom = c.post("/api/personas", json={"name": "Mom"}).json()
        bob = c.post("/api/personas", json={"name": "Bob"}).json()  # NOT a member
        h = {"X-Persona-Id": mom["id"]}
        trip = c.post("/api/trips", json={"name": "US"}, headers=h).json()
        # Mom pays for something; Bob pays nothing and isn't on the trip.
        c.post(
            "/api/receipts",
            data={"payload": json.dumps({"trip_id": trip["id"], "currency": "INR", "total": 218.0})},
            files={"file": ("r.jpg", io.BytesIO(b"x"), "image/jpeg")},
            headers=h,
        )
        r = c.post(
            f"/api/trips/{trip['id']}/ask",
            json={"question": "how much did Bob pay?"},
            headers=h,
        )
        # Planner saw Bob even though he's not a member ...
        assert "Bob" in recorder.seen_context.people
        # ... so the answer is Bob's 0, NOT Mom's 218.
        body = r.json()
        assert body["value"] == 0.0
        assert body["matched"] == []
    finally:
        app.dependency_overrides.clear()


# --- conversation history (follow-up context for the planner) ---------------

def _ctx(history=None):
    return AskContext(
        today=date(2026, 7, 20),
        base_currency="INR",
        categories=["dining", "fuel"],
        people=["Mom", "Dad"],
        history=history or [],
    )


# the rendered history block starts with this header (the prompt's static rule
# also mentions "Recent conversation", so assert on the header, not that phrase).
_HIST_HEADER = "oldest first — use only to resolve"


def test_prompt_omits_history_block_when_empty():
    prompt = build_planner_prompt(_ctx())
    assert _HIST_HEADER not in prompt


def test_prompt_includes_recent_turns():
    hist = [
        AskTurn(question="how much did Dad pay?", answer="Dad paid 350."),
        AskTurn(question="and on dining?", answer="150 on dining, paid by Dad."),
    ]
    prompt = build_planner_prompt(_ctx(hist))
    assert _HIST_HEADER in prompt
    assert "how much did Dad pay?" in prompt
    assert "and on dining?" in prompt


def test_prompt_history_is_bounded_to_recent_turns():
    hist = [AskTurn(question=f"q{i}", answer=f"a{i}") for i in range(10)]
    prompt = build_planner_prompt(_ctx(hist))
    # only the last 6 turns are rendered; the oldest are dropped
    assert "q0" not in prompt and "q3" not in prompt
    assert "q4" in prompt and "q9" in prompt


def test_ask_endpoint_forwards_history_to_planner():
    """A follow-up question must reach the planner WITH the prior turns, else
    'and on dining?' can't be resolved. The executor never sees history."""
    repo = InMemoryRepository()
    recorder = RecordingPlanner(QuerySpec(operation="sum", category="dining"))
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_storage] = lambda: NoopStorage()
    app.dependency_overrides[get_fx] = lambda: FakeFx(rate=1.0)
    app.dependency_overrides[get_ask_planner] = lambda: recorder
    try:
        c = TestClient(app)
        mom = c.post("/api/personas", json={"name": "Mom"}).json()
        h = {"X-Persona-Id": mom["id"]}
        trip = c.post("/api/trips", json={"name": "Goa"}, headers=h).json()
        c.post(
            f"/api/trips/{trip['id']}/ask",
            json={
                "question": "and on dining?",
                "history": [
                    {"question": "how much did we spend?", "answer": "800 total."}
                ],
            },
            headers=h,
        )
        assert len(recorder.seen_context.history) == 1
        assert recorder.seen_context.history[0].question == "how much did we spend?"
    finally:
        app.dependency_overrides.clear()


def test_summary_endpoint(client):
    mom = client.post("/api/personas", json={"name": "Mom"}).json()
    h = {"X-Persona-Id": mom["id"]}
    trip = client.post("/api/trips", json={"name": "Trip"}, headers=h).json()
    client.post(
        "/api/receipts",
        data={"payload": json.dumps({"trip_id": trip["id"], "currency": "INR", "total": 90})},
        files={"file": ("r.jpg", io.BytesIO(b"x"), "image/jpeg")},
        headers=h,
    )
    s = client.get(f"/api/trips/{trip['id']}/summary", headers=h).json()
    assert s["total"] == 90.0
    assert s["per_person"][0]["persona_id"] == mom["id"]
