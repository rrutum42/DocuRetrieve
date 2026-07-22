"""Receipt save/read + visibility tests, driven through the HTTP layer with the
in-memory repository and no-op storage injected. Covers the security-critical
cases: you can't save into or read another persona's container.
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from app.deps import get_repository, get_storage
from app.main import app
from app.repository import InMemoryRepository
from app.storage import NoopStorage


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def client(repo):
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_storage] = lambda: NoopStorage()
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
    r = _save_receipt(client, mom["id"], {"trip_id": None, "total": 3})
    rid = r.json()["id"]
    d = client.delete(f"/api/receipts/{rid}", headers={"X-Persona-Id": mom["id"]})
    assert d.status_code == 204
    assert (
        client.get(
            f"/api/receipts/{rid}", headers={"X-Persona-Id": mom["id"]}
        ).status_code
        == 404
    )
