"""API-level tests for personas + trips, driven through FastAPI with the
in-memory repository injected via dependency override. Verifies the wire
contract and that the persona header actually gates access at the HTTP layer.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.deps import get_repository
from app.main import app
from app.repository import InMemoryRepository


@pytest.fixture
def client():
    repo = InMemoryRepository()
    app.dependency_overrides[get_repository] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_persona(client, name):
    return client.post("/api/personas", json={"name": name}).json()


def test_persona_create_and_list(client):
    mom = _make_persona(client, "Mom")
    assert mom["name"] == "Mom" and mom["id"]
    names = [p["name"] for p in client.get("/api/personas").json()]
    assert "Mom" in names


def test_trips_require_a_persona_header(client):
    # No X-Persona-Id -> 401
    assert client.get("/api/trips").status_code == 401


def test_unknown_persona_header_is_rejected(client):
    r = client.get("/api/trips", headers={"X-Persona-Id": "nope"})
    assert r.status_code == 401


def test_create_and_list_trip_scoped_to_persona(client):
    mom = _make_persona(client, "Mom")
    h = {"X-Persona-Id": mom["id"]}
    created = client.post("/api/trips", json={"name": "France"}, headers=h).json()
    assert created["name"] == "France"
    assert mom["id"] in created["member_ids"]  # creator auto-membered

    trips = client.get("/api/trips", headers=h).json()
    assert [t["id"] for t in trips] == [created["id"]]


def test_stranger_gets_404_on_someone_elses_trip(client):
    mom = _make_persona(client, "Mom")
    kid = _make_persona(client, "Kid")
    trip = client.post(
        "/api/trips", json={"name": "France"}, headers={"X-Persona-Id": mom["id"]}
    ).json()

    # Kid can't see it — and we return 404 (not 403) so we don't leak existence.
    r = client.get(f"/api/trips/{trip['id']}", headers={"X-Persona-Id": kid["id"]})
    assert r.status_code == 404
    assert client.get("/api/trips", headers={"X-Persona-Id": kid["id"]}).json() == []


def test_creator_can_delete_trip(client):
    mom = _make_persona(client, "Mom")
    h = {"X-Persona-Id": mom["id"]}
    trip = client.post("/api/trips", json={"name": "France"}, headers=h).json()
    assert client.delete(f"/api/trips/{trip['id']}", headers=h).status_code == 204
    assert client.get("/api/trips", headers=h).json() == []


def test_non_creator_member_cannot_delete_trip(client):
    mom = _make_persona(client, "Mom")
    dad = _make_persona(client, "Dad")
    trip = client.post(
        "/api/trips",
        json={"name": "France", "member_ids": [dad["id"]]},
        headers={"X-Persona-Id": mom["id"]},
    ).json()
    # Dad is a member (can see it) but not the creator -> 403, trip survives.
    r = client.delete(f"/api/trips/{trip['id']}", headers={"X-Persona-Id": dad["id"]})
    assert r.status_code == 403
    assert trip["id"] in [
        t["id"]
        for t in client.get("/api/trips", headers={"X-Persona-Id": dad["id"]}).json()
    ]


def test_stranger_deleting_trip_gets_404(client):
    mom = _make_persona(client, "Mom")
    kid = _make_persona(client, "Kid")
    trip = client.post(
        "/api/trips", json={"name": "France"}, headers={"X-Persona-Id": mom["id"]}
    ).json()
    # Kid can't see it -> 404 (existence not leaked as 403)
    r = client.delete(f"/api/trips/{trip['id']}", headers={"X-Persona-Id": kid["id"]})
    assert r.status_code == 404


def test_add_members_shares_the_trip(client):
    mom = _make_persona(client, "Mom")
    dad = _make_persona(client, "Dad")
    trip = client.post(
        "/api/trips", json={"name": "France"}, headers={"X-Persona-Id": mom["id"]}
    ).json()

    r = client.post(
        f"/api/trips/{trip['id']}/members",
        json={"member_ids": [dad["id"]]},
        headers={"X-Persona-Id": mom["id"]},
    )
    assert r.status_code == 200
    dad_trips = client.get(
        "/api/trips", headers={"X-Persona-Id": dad["id"]}
    ).json()
    assert trip["id"] in [t["id"] for t in dad_trips]
