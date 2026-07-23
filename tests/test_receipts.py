"""Receipt save/read + visibility tests, driven through the HTTP layer with the
in-memory repository and no-op storage injected. Covers the security-critical
cases: you can't save into or read another persona's container.
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from app.deps import get_fx, get_repository, get_storage
from app.fx import Conversion
from app.main import app
from app.repository import InMemoryRepository
from app.storage import NoopStorage


class FakeFx:
    """Deterministic conversion for tests. rate=None simulates a conversion
    failure (unsupported currency / FX service down)."""

    def __init__(self, rate=80.0):
        self.rate = rate

    def convert(self, amount, from_currency, to_currency, on):
        if (from_currency or "").upper() == (to_currency or "").upper():
            return Conversion(round(amount, 2), 1.0, on)
        if self.rate is None:
            return None
        return Conversion(round(amount * self.rate, 2), self.rate, on)


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def fx():
    return FakeFx()


@pytest.fixture
def client(repo, fx):
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_storage] = lambda: NoopStorage()
    app.dependency_overrides[get_fx] = lambda: fx
    yield TestClient(app)
    app.dependency_overrides.clear()


def _persona(client, name):
    return client.post("/api/personas", json={"name": name}).json()


def _fake_image():
    return ("r.jpg", io.BytesIO(b"\xff\xd8\xff fake jpeg"), "image/jpeg")


def _save_receipt(client, persona_id, payload):
    return client.post(
        "/api/receipts",
        data={"payload": json.dumps(payload)},
        files={"file": _fake_image()},
        headers={"X-Persona-Id": persona_id},
    )


def test_save_and_list_receipt_in_trip(client):
    mom = _persona(client, "Mom")
    h = {"X-Persona-Id": mom["id"]}
    trip = client.post("/api/trips", json={"name": "France"}, headers=h).json()

    r = _save_receipt(
        client,
        mom["id"],
        {
            "trip_id": trip["id"],
            "paid_by_persona_id": mom["id"],
            "merchant": "Boulangerie",
            "currency": "EUR",
            "total": 12.4,
            "category": "dining",
            "line_items": [{"description": "Croissant", "amount": 2.2}],
        },
    )
    assert r.status_code == 201, r.text
    saved = r.json()
    assert saved["merchant"] == "Boulangerie"
    assert saved["paid_by_persona_id"] == mom["id"]
    assert saved["status"] == "confirmed"
    assert len(saved["line_items"]) == 1

    listed = client.get(f"/api/trips/{trip['id']}/receipts", headers=h).json()
    assert [x["id"] for x in listed] == [saved["id"]]


def test_receipt_converts_to_trip_base_currency(client):
    mom = _persona(client, "Mom")
    h = {"X-Persona-Id": mom["id"]}
    # Trip base currency INR (default); receipt in USD -> converts at FakeFx rate 80
    trip = client.post("/api/trips", json={"name": "US road trip"}, headers=h).json()
    assert trip["base_currency"] == "INR"

    r = _save_receipt(
        client,
        mom["id"],
        {"trip_id": trip["id"], "currency": "USD", "total": 10.0, "category": "fuel"},
    ).json()
    assert r["base_currency"] == "INR"
    assert r["base_amount"] == 800.0
    assert r["fx_rate"] == 80.0


def test_same_currency_receipt_keeps_amount(client):
    mom = _persona(client, "Mom")
    h = {"X-Persona-Id": mom["id"]}
    trip = client.post(
        "/api/trips", json={"name": "Delhi", "base_currency": "INR"}, headers=h
    ).json()
    r = _save_receipt(
        client, mom["id"], {"trip_id": trip["id"], "currency": "INR", "total": 250.0}
    ).json()
    assert r["base_amount"] == 250.0
    assert r["fx_rate"] == 1.0


def test_conversion_failure_saves_native_only(client, fx):
    fx.rate = None  # simulate FX service down / unsupported currency
    mom = _persona(client, "Mom")
    h = {"X-Persona-Id": mom["id"]}
    trip = client.post("/api/trips", json={"name": "Trip"}, headers=h).json()
    r = _save_receipt(
        client, mom["id"], {"trip_id": trip["id"], "currency": "USD", "total": 10.0}
    ).json()
    # Native amount preserved; conversion fields empty; receipt still saved.
    assert r["total"] == 10.0
    assert r["base_currency"] == "INR"
    assert r["base_amount"] is None
    assert r["fx_rate"] is None


def test_zero_total_is_rejected(client):
    mom = _persona(client, "Mom")
    r = _save_receipt(client, mom["id"], {"trip_id": None, "currency": "INR", "total": 0})
    assert r.status_code == 422
    assert "greater than 0" in str(r.json()["detail"])


def test_missing_total_is_rejected(client):
    mom = _persona(client, "Mom")
    r = _save_receipt(client, mom["id"], {"trip_id": None, "currency": "INR"})
    assert r.status_code == 422


def test_negative_total_is_rejected(client):
    mom = _persona(client, "Mom")
    r = _save_receipt(client, mom["id"], {"trip_id": None, "currency": "INR", "total": -5})
    assert r.status_code == 422


def test_invalid_category_is_rejected(client):
    mom = _persona(client, "Mom")
    trip = client.post(
        "/api/trips", json={"name": "France"}, headers={"X-Persona-Id": mom["id"]}
    ).json()
    r = _save_receipt(
        client, mom["id"], {"trip_id": trip["id"], "category": "not-real"}
    )
    assert r.status_code == 422


def test_non_image_upload_rejected(client):
    mom = _persona(client, "Mom")
    r = client.post(
        "/api/receipts",
        data={"payload": json.dumps({})},
        files={"file": ("x.txt", io.BytesIO(b"hi"), "text/plain")},
        headers={"X-Persona-Id": mom["id"]},
    )
    assert r.status_code == 415


def test_cannot_save_into_trip_you_cannot_see(client):
    mom = _persona(client, "Mom")
    kid = _persona(client, "Kid")
    trip = client.post(
        "/api/trips", json={"name": "France"}, headers={"X-Persona-Id": mom["id"]}
    ).json()
    # Kid is not on the trip -> saving into it is a 404
    r = _save_receipt(client, kid["id"], {"trip_id": trip["id"], "total": 5})
    assert r.status_code == 404


def test_paid_by_must_be_a_trip_member(client):
    mom = _persona(client, "Mom")
    stranger = _persona(client, "Stranger")
    trip = client.post(
        "/api/trips", json={"name": "France"}, headers={"X-Persona-Id": mom["id"]}
    ).json()
    r = _save_receipt(
        client,
        mom["id"],
        {"trip_id": trip["id"], "paid_by_persona_id": stranger["id"], "total": 5},
    )
    assert r.status_code == 400


def test_personal_ledger_is_private(client):
    mom = _persona(client, "Mom")
    kid = _persona(client, "Kid")
    # Mom saves a trip-less personal receipt
    r = _save_receipt(client, mom["id"], {"trip_id": None, "total": 9.99})
    assert r.status_code == 201
    rid = r.json()["id"]

    # Mom sees it in her personal ledger; Kid does not, and can't fetch it.
    assert rid in [
        x["id"]
        for x in client.get(
            "/api/receipts/personal", headers={"X-Persona-Id": mom["id"]}
        ).json()
    ]
    assert (
        client.get("/api/receipts/personal", headers={"X-Persona-Id": kid["id"]}).json()
        == []
    )
    assert (
        client.get(
            f"/api/receipts/{rid}", headers={"X-Persona-Id": kid["id"]}
        ).status_code
        == 404
    )


def test_delete_receipt(client):
    mom = _persona(client, "Mom")
    r = _save_receipt(client, mom["id"], {"trip_id": None, "currency": "INR", "total": 3})
    rid = r.json()["id"]
    d = client.delete(f"/api/receipts/{rid}", headers={"X-Persona-Id": mom["id"]})
    assert d.status_code == 204
    assert (
        client.get(
            f"/api/receipts/{rid}", headers={"X-Persona-Id": mom["id"]}
        ).status_code
        == 404
    )


def test_sparse_receipt_is_flagged_server_side(client):
    # A client POSTs a bare amount with NO low_confidence_fields (trying to hide
    # it) — the server re-validates and flags authenticity anyway.
    mom = _persona(client, "Mom")
    r = _save_receipt(
        client,
        mom["id"],
        {"trip_id": None, "currency": "INR", "total": 5000, "low_confidence_fields": []},
    ).json()
    assert "authenticity" in r["low_confidence_fields"]


def test_normal_receipt_not_flagged_server_side(client):
    mom = _persona(client, "Mom")
    r = _save_receipt(
        client,
        mom["id"],
        {
            "trip_id": None,
            "merchant": "Cafe",
            "purchase_date": "2026-06-01",
            "currency": "INR",
            "subtotal": 90,
            "tax": 10,
            "total": 100,
        },
    ).json()
    assert "authenticity" not in r["low_confidence_fields"]


def test_member_can_dispute_and_resolve(client):
    mom = _persona(client, "Mom")
    dad = _persona(client, "Dad")
    trip = client.post(
        "/api/trips",
        json={"name": "Goa", "member_ids": [dad["id"]]},
        headers={"X-Persona-Id": mom["id"]},
    ).json()
    # Mom saves a suspicious-looking receipt
    r = _save_receipt(
        client, mom["id"], {"trip_id": trip["id"], "currency": "INR", "total": 5000}
    ).json()

    # Dad (a member) disputes it
    d = client.post(
        f"/api/receipts/{r['id']}/dispute",
        json={"reason": "This is just a number on paper, not a real receipt."},
        headers={"X-Persona-Id": dad["id"]},
    )
    assert d.status_code == 200
    assert d.json()["disputed_by_persona_id"] == dad["id"]
    assert "number on paper" in d.json()["dispute_reason"]

    # Resolve clears it
    res = client.delete(
        f"/api/receipts/{r['id']}/dispute", headers={"X-Persona-Id": mom["id"]}
    )
    assert res.status_code == 200
    assert res.json()["disputed_by_persona_id"] is None


def test_stranger_cannot_dispute(client):
    mom = _persona(client, "Mom")
    kid = _persona(client, "Kid")  # not on the trip
    trip = client.post(
        "/api/trips", json={"name": "Goa"}, headers={"X-Persona-Id": mom["id"]}
    ).json()
    r = _save_receipt(
        client, mom["id"], {"trip_id": trip["id"], "currency": "INR", "total": 100}
    ).json()
    # Kid can't see the trip -> can't dispute
    d = client.post(
        f"/api/receipts/{r['id']}/dispute",
        json={"reason": "nope"},
        headers={"X-Persona-Id": kid["id"]},
    )
    assert d.status_code == 404
