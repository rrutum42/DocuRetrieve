"""Visibility rule tests — the security-critical part of Day 2.

A persona must see only trips they created or were shared into, and must not be
able to read or modify anyone else's. These run against the in-memory repository
(no database), so the rule itself is verified in isolation.
"""

from __future__ import annotations

import pytest

from app.repository import Forbidden, InMemoryRepository, NotFound, SupabaseRepository


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def people(repo):
    mom = repo.create_persona("Mom", "#e11")
    dad = repo.create_persona("Dad", "#11e")
    kid = repo.create_persona("Kid", "#1e1")
    return mom, dad, kid


def test_creator_sees_own_trip(repo, people):
    mom, dad, kid = people
    trip = repo.create_trip(
        name="France", created_by=mom.id, start_date=None, end_date=None,
        cover_image=None, member_ids=[],
    )
    assert trip.id in {t.id for t in repo.list_trips_for_persona(mom.id)}


def test_creator_is_always_a_member(repo, people):
    mom, *_ = people
    trip = repo.create_trip(
        name="France", created_by=mom.id, start_date=None, end_date=None,
        cover_image=None, member_ids=[],
    )
    assert mom.id in trip.member_ids


# --- malformed ids must be "not found", never a 500 -------------------------
# Regression: a non-UUID id (e.g. a spoofed/garbage X-Persona-Id or trip path
# param) reaches a Postgres `uuid` column, which raises "invalid input syntax"
# -> an unhandled 500. The guard must resolve these to None / NotFound WITHOUT
# ever querying the DB. A fake client that explodes on use proves the short-circuit.

class _ExplodingClient:
    """Any DB access is a test failure — the guard must return before this."""

    def table(self, *_a, **_k):  # pragma: no cover - must never be called
        raise AssertionError("DB was queried for a malformed id")


@pytest.fixture
def supa():
    return SupabaseRepository(_ExplodingClient())


@pytest.mark.parametrize("bad_id", ["not-a-real-id", "", "'; DROP TABLE personas;--", "123"])
def test_supabase_malformed_persona_id_is_none_not_500(supa, bad_id):
    assert supa.get_persona(bad_id) is None  # -> current_persona raises 401, not 500


@pytest.mark.parametrize("bad_id", ["not-a-real-id", "abc", "0 OR 1=1"])
def test_supabase_malformed_trip_id_is_notfound_not_500(supa, bad_id):
    with pytest.raises(NotFound):
        supa.get_trip_for_persona(bad_id, "some-persona")


def test_supabase_malformed_receipt_id_is_notfound_not_500(supa):
    with pytest.raises(NotFound):
        supa.get_receipt("not-a-uuid", "some-persona")


def test_supabase_valid_uuid_does_reach_the_db(supa):
    # A well-formed UUID must pass the guard and actually hit the DB (which here
    # explodes) — proving the guard rejects only malformed ids, not real lookups.
    with pytest.raises(AssertionError, match="DB was queried"):
        supa.get_persona("123e4567-e89b-12d3-a456-426614174000")


def test_shared_member_sees_trip_but_stranger_does_not(repo, people):
    mom, dad, kid = people
    trip = repo.create_trip(
        name="France", created_by=mom.id, start_date=None, end_date=None,
        cover_image=None, member_ids=[dad.id],
    )
    dad_trips = {t.id for t in repo.list_trips_for_persona(dad.id)}
    kid_trips = {t.id for t in repo.list_trips_for_persona(kid.id)}
    assert trip.id in dad_trips           # shared -> visible
    assert trip.id not in kid_trips       # not shared -> invisible


def test_stranger_get_raises_forbidden_not_notfound(repo, people):
    mom, dad, kid = people
    trip = repo.create_trip(
        name="France", created_by=mom.id, start_date=None, end_date=None,
        cover_image=None, member_ids=[dad.id],
    )
    # kid is not a member — must not be able to read it
    with pytest.raises(Forbidden):
        repo.get_trip_for_persona(trip.id, kid.id)


def test_missing_trip_raises_notfound(repo, people):
    mom, *_ = people
    with pytest.raises(NotFound):
        repo.get_trip_for_persona("does-not-exist", mom.id)


def test_stranger_cannot_add_members(repo, people):
    mom, dad, kid = people
    trip = repo.create_trip(
        name="France", created_by=mom.id, start_date=None, end_date=None,
        cover_image=None, member_ids=[],
    )
    # kid can't see it, so kid can't mutate it
    with pytest.raises(Forbidden):
        repo.add_trip_members(trip.id, kid.id, [kid.id])


def test_adding_a_member_grants_them_visibility(repo, people):
    mom, dad, kid = people
    trip = repo.create_trip(
        name="France", created_by=mom.id, start_date=None, end_date=None,
        cover_image=None, member_ids=[],
    )
    assert trip.id not in {t.id for t in repo.list_trips_for_persona(kid.id)}
    repo.add_trip_members(trip.id, mom.id, [kid.id])
    assert trip.id in {t.id for t in repo.list_trips_for_persona(kid.id)}


def test_member_ids_are_deduped(repo, people):
    mom, dad, kid = people
    trip = repo.create_trip(
        name="France", created_by=mom.id, start_date=None, end_date=None,
        cover_image=None, member_ids=[dad.id, dad.id],
    )
    repo.add_trip_members(trip.id, mom.id, [dad.id, kid.id])
    updated = repo.get_trip_for_persona(trip.id, mom.id)
    assert sorted(updated.member_ids) == sorted({mom.id, dad.id, kid.id})
