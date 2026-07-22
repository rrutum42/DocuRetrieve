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

from app.api_models import Persona, Receipt
from app.ask import AskPlanner, QuerySpec, run_query
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


def test_no_match_is_graceful():
    r = run_query(
        "fuel spend", QuerySpec(operation="sum", category="fuel"), RECEIPTS, PEOPLE, "INR"
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
