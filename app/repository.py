"""Data access for personas and trips, behind a small interface.

The interface (Repository) has two implementations:

  * InMemoryRepository  — used by tests and as a no-Supabase local fallback.
  * SupabaseRepository  — the live Postgres-backed implementation.

The trip visibility rule lives here, in one place, and is exercised by unit
tests against the in-memory implementation (no database required):

    persona P sees trip T  iff  T.created_by == P  OR  P in T.members
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Protocol

from .api_models import Persona, Trip


class NotFound(Exception):
    """Raised when an entity does not exist."""


class Forbidden(Exception):
    """Raised when a persona may not see/modify a trip (visibility rule)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Repository(Protocol):
    # personas
    def list_personas(self) -> list[Persona]: ...
    def create_persona(self, name: str, color: str | None) -> Persona: ...
    def get_persona(self, persona_id: str) -> Persona | None: ...

    # trips
    def list_trips_for_persona(self, persona_id: str) -> list[Trip]: ...
    def create_trip(
        self,
        *,
        name: str,
        created_by: str,
        start_date: date | None,
        end_date: date | None,
        cover_image: str | None,
        member_ids: list[str],
    ) -> Trip: ...
    def get_trip_for_persona(self, trip_id: str, persona_id: str) -> Trip: ...
    def add_trip_members(
        self, trip_id: str, persona_id: str, member_ids: list[str]
    ) -> Trip: ...


# --------------------------------------------------------------------------- #
# In-memory implementation (tests / offline dev)
# --------------------------------------------------------------------------- #

class InMemoryRepository:
    def __init__(self) -> None:
        self._personas: dict[str, Persona] = {}
        self._trips: dict[str, Trip] = {}

    # personas
    def list_personas(self) -> list[Persona]:
        return sorted(self._personas.values(), key=lambda p: p.created_at or _now())

    def create_persona(self, name: str, color: str | None) -> Persona:
        pid = str(uuid.uuid4())
        p = Persona(id=pid, name=name, color=color, created_at=_now())
        self._personas[pid] = p
        return p

    def get_persona(self, persona_id: str) -> Persona | None:
        return self._personas.get(persona_id)

    # trips
    def _visible(self, trip: Trip, persona_id: str) -> bool:
        return trip.created_by == persona_id or persona_id in trip.member_ids

    def list_trips_for_persona(self, persona_id: str) -> list[Trip]:
        return [t for t in self._trips.values() if self._visible(t, persona_id)]

    def create_trip(
        self,
        *,
        name: str,
        created_by: str,
        start_date: date | None,
        end_date: date | None,
        cover_image: str | None,
        member_ids: list[str],
    ) -> Trip:
        tid = str(uuid.uuid4())
        # Creator is always a member; de-dupe.
        members = list(dict.fromkeys([created_by, *member_ids]))
        t = Trip(
            id=tid,
            name=name,
            start_date=start_date,
            end_date=end_date,
            cover_image=cover_image,
            created_by=created_by,
            member_ids=members,
            created_at=_now(),
        )
        self._trips[tid] = t
        return t

    def get_trip_for_persona(self, trip_id: str, persona_id: str) -> Trip:
        trip = self._trips.get(trip_id)
        if trip is None:
            raise NotFound(trip_id)
        if not self._visible(trip, persona_id):
            raise Forbidden(trip_id)
        return trip

    def add_trip_members(
        self, trip_id: str, persona_id: str, member_ids: list[str]
    ) -> Trip:
        trip = self.get_trip_for_persona(trip_id, persona_id)  # enforces visibility
        merged = list(dict.fromkeys([*trip.member_ids, *member_ids]))
        updated = trip.model_copy(update={"member_ids": merged})
        self._trips[trip_id] = updated
        return updated


# --------------------------------------------------------------------------- #
# Supabase implementation (live)
# --------------------------------------------------------------------------- #

class SupabaseRepository:
    """Postgres-backed via Supabase's REST client.

    Membership is stored in the trip_members join table; this class assembles
    Trip.member_ids from it so the rest of the app never sees the join.
    """

    def __init__(self, client) -> None:
        self._db = client

    # personas
    def list_personas(self) -> list[Persona]:
        rows = self._db.table("personas").select("*").order("created_at").execute().data
        return [Persona(**r) for r in rows]

    def create_persona(self, name: str, color: str | None) -> Persona:
        row = (
            self._db.table("personas")
            .insert({"name": name, "color": color})
            .execute()
            .data[0]
        )
        return Persona(**row)

    def get_persona(self, persona_id: str) -> Persona | None:
        rows = (
            self._db.table("personas").select("*").eq("id", persona_id).execute().data
        )
        return Persona(**rows[0]) if rows else None

    # trips
    def _member_ids(self, trip_id: str) -> list[str]:
        rows = (
            self._db.table("trip_members")
            .select("persona_id")
            .eq("trip_id", trip_id)
            .execute()
            .data
        )
        return [r["persona_id"] for r in rows]

    def _to_trip(self, row: dict) -> Trip:
        return Trip(**row, member_ids=self._member_ids(row["id"]))

    def list_trips_for_persona(self, persona_id: str) -> list[Trip]:
        # trips this persona is a member of ...
        member_rows = (
            self._db.table("trip_members")
            .select("trip_id")
            .eq("persona_id", persona_id)
            .execute()
            .data
        )
        member_trip_ids = {r["trip_id"] for r in member_rows}

        # ... plus trips they created (covers creator even before membership row).
        created = (
            self._db.table("trips")
            .select("*")
            .eq("created_by", persona_id)
            .execute()
            .data
        )
        seen = {r["id"] for r in created}
        trips = list(created)

        missing = [tid for tid in member_trip_ids if tid not in seen]
        if missing:
            more = (
                self._db.table("trips")
                .select("*")
                .in_("id", missing)
                .execute()
                .data
            )
            trips.extend(more)

        trips.sort(key=lambda r: r.get("created_at") or "")
        return [self._to_trip(r) for r in trips]

    def create_trip(
        self,
        *,
        name: str,
        created_by: str,
        start_date: date | None,
        end_date: date | None,
        cover_image: str | None,
        member_ids: list[str],
    ) -> Trip:
        row = (
            self._db.table("trips")
            .insert(
                {
                    "name": name,
                    "created_by": created_by,
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None,
                    "cover_image": cover_image,
                }
            )
            .execute()
            .data[0]
        )
        members = list(dict.fromkeys([created_by, *member_ids]))
        self._db.table("trip_members").insert(
            [{"trip_id": row["id"], "persona_id": pid} for pid in members]
        ).execute()
        return Trip(**row, member_ids=members)

    def get_trip_for_persona(self, trip_id: str, persona_id: str) -> Trip:
        rows = self._db.table("trips").select("*").eq("id", trip_id).execute().data
        if not rows:
            raise NotFound(trip_id)
        trip = self._to_trip(rows[0])
        if trip.created_by != persona_id and persona_id not in trip.member_ids:
            raise Forbidden(trip_id)
        return trip

    def add_trip_members(
        self, trip_id: str, persona_id: str, member_ids: list[str]
    ) -> Trip:
        trip = self.get_trip_for_persona(trip_id, persona_id)  # enforces visibility
        new_ids = [pid for pid in member_ids if pid not in trip.member_ids]
        if new_ids:
            self._db.table("trip_members").insert(
                [{"trip_id": trip_id, "persona_id": pid} for pid in new_ids]
            ).execute()
        return trip.model_copy(
            update={"member_ids": [*trip.member_ids, *new_ids]}
        )
