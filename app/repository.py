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

from .api_models import Persona, Receipt, ReceiptCreate, ReceiptLineItem, Trip
from .storage import signed_url, signed_urls


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
        base_currency: str = "INR",
        member_ids: list[str],
    ) -> Trip: ...
    def get_trip_for_persona(self, trip_id: str, persona_id: str) -> Trip: ...
    def add_trip_members(
        self, trip_id: str, persona_id: str, member_ids: list[str]
    ) -> Trip: ...
    def delete_trip(self, trip_id: str, persona_id: str) -> None: ...

    # receipts
    def create_receipt(
        self,
        *,
        owner_persona_id: str,
        data: ReceiptCreate,
        image_path: str | None,
        base_currency: str | None = None,
        base_amount: float | None = None,
        fx_rate: float | None = None,
        fx_date: date | None = None,
    ) -> Receipt: ...
    def list_trip_receipts(self, trip_id: str, persona_id: str) -> list[Receipt]: ...
    def list_personal_receipts(self, persona_id: str) -> list[Receipt]: ...
    def get_receipt(self, receipt_id: str, persona_id: str) -> Receipt: ...
    def delete_receipt(self, receipt_id: str, persona_id: str) -> None: ...
    def set_dispute(
        self, receipt_id: str, persona_id: str, reason: str | None
    ) -> Receipt: ...


# --------------------------------------------------------------------------- #
# In-memory implementation (tests / offline dev)
# --------------------------------------------------------------------------- #

class InMemoryRepository:
    def __init__(self) -> None:
        self._personas: dict[str, Persona] = {}
        self._trips: dict[str, Trip] = {}
        self._receipts: dict[str, Receipt] = {}

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
        base_currency: str = "INR",
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
            base_currency=base_currency,
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

    def delete_trip(self, trip_id: str, persona_id: str) -> None:
        trip = self._trips.get(trip_id)
        if trip is None:
            raise NotFound(trip_id)
        if trip.created_by != persona_id:
            raise Forbidden(trip_id)  # only the creator may delete
        # Remove the trip and all its receipts (cascade equivalent).
        self._receipts = {
            rid: r for rid, r in self._receipts.items() if r.trip_id != trip_id
        }
        self._trips.pop(trip_id, None)

    # receipts
    def create_receipt(
        self,
        *,
        owner_persona_id: str,
        data: ReceiptCreate,
        image_path: str | None,
        base_currency: str | None = None,
        base_amount: float | None = None,
        fx_rate: float | None = None,
        fx_date: date | None = None,
    ) -> Receipt:
        if data.trip_id is not None:
            self.get_trip_for_persona(data.trip_id, owner_persona_id)  # visibility
        rid = str(uuid.uuid4())
        receipt = Receipt(
            id=rid,
            trip_id=data.trip_id,
            owner_persona_id=owner_persona_id,
            paid_by_persona_id=data.paid_by_persona_id or owner_persona_id,
            merchant=data.merchant,
            purchase_date=data.purchase_date,
            currency=data.currency,
            subtotal=data.subtotal,
            tax=data.tax,
            tip=data.tip,
            total=data.total,
            category=data.category,
            payment_method=data.payment_method,
            line_items=list(data.line_items),
            low_confidence_fields=list(data.low_confidence_fields),
            image_path=image_path,
            image_url=image_path,  # in-memory has no signing
            status="confirmed",
            created_at=_now(),
            base_currency=base_currency,
            base_amount=base_amount,
            fx_rate=fx_rate,
            fx_date=fx_date,
        )
        self._receipts[rid] = receipt
        return receipt

    def _receipt_visible(self, r: Receipt, persona_id: str) -> bool:
        if r.trip_id is None:
            return r.owner_persona_id == persona_id
        trip = self._trips.get(r.trip_id)
        return bool(trip and self._visible(trip, persona_id))

    def list_trip_receipts(self, trip_id: str, persona_id: str) -> list[Receipt]:
        self.get_trip_for_persona(trip_id, persona_id)  # enforces visibility
        return [
            r for r in self._receipts.values() if r.trip_id == trip_id
        ]

    def list_personal_receipts(self, persona_id: str) -> list[Receipt]:
        return [
            r
            for r in self._receipts.values()
            if r.trip_id is None and r.owner_persona_id == persona_id
        ]

    def get_receipt(self, receipt_id: str, persona_id: str) -> Receipt:
        r = self._receipts.get(receipt_id)
        if r is None:
            raise NotFound(receipt_id)
        if not self._receipt_visible(r, persona_id):
            raise Forbidden(receipt_id)
        return r

    def delete_receipt(self, receipt_id: str, persona_id: str) -> None:
        self.get_receipt(receipt_id, persona_id)  # enforces visibility
        self._receipts.pop(receipt_id, None)

    def set_dispute(
        self, receipt_id: str, persona_id: str, reason: str | None
    ) -> Receipt:
        r = self.get_receipt(receipt_id, persona_id)  # enforces visibility
        updated = r.model_copy(
            update={
                "disputed_by_persona_id": persona_id if reason else None,
                "dispute_reason": reason,
            }
        )
        self._receipts[receipt_id] = updated
        return updated


# --------------------------------------------------------------------------- #
# Supabase implementation (live)
# --------------------------------------------------------------------------- #

def _is_uuid(value: str) -> bool:
    """True if `value` is a well-formed UUID. Client-supplied ids (persona
    header, trip/receipt path params) hit `uuid` columns in Postgres, which
    *raises* on a malformed string ("invalid input syntax for type uuid") — a
    500. A malformed id can never match a real row, so we treat it as "not
    found" and let the normal 404/401 path handle it. Never leak existence."""
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


class SupabaseRepository:
    """Postgres-backed via Supabase's REST client.

    Membership is stored in the trip_members join table; this class assembles
    Trip.member_ids from it so the rest of the app never sees the join.
    """

    def __init__(self, client) -> None:
        self._db = client

    # receipts ---------------------------------------------------------------

    def _row_to_receipt(self, row: dict, line_rows: list[dict], image_url) -> Receipt:
        conf = row.get("confidence")
        lcf = conf.get("low_confidence_fields", []) if isinstance(conf, dict) else []
        return Receipt(
            id=row["id"],
            trip_id=row.get("trip_id"),
            owner_persona_id=row["owner_persona_id"],
            paid_by_persona_id=row["paid_by_persona_id"],
            merchant=row.get("merchant"),
            purchase_date=row.get("purchase_date"),
            currency=row.get("currency"),
            subtotal=row.get("subtotal"),
            tax=row.get("tax"),
            tip=row.get("tip"),
            total=row.get("total"),
            category=row.get("category"),
            payment_method=row.get("payment_method"),
            line_items=[
                ReceiptLineItem(
                    description=li.get("description") or "",
                    qty=li.get("qty"),
                    unit_price=li.get("unit_price"),
                    amount=li.get("amount"),
                )
                for li in line_rows
            ],
            low_confidence_fields=lcf,
            image_path=row.get("image_path"),
            image_url=image_url,
            status=row.get("status", "confirmed"),
            created_at=row.get("created_at"),
            base_currency=row.get("base_currency"),
            base_amount=row.get("base_amount"),
            fx_rate=row.get("fx_rate"),
            fx_date=row.get("fx_date"),
            disputed_by_persona_id=row.get("disputed_by_persona_id"),
            dispute_reason=row.get("dispute_reason"),
        )

    def _assemble(self, rows: list[dict]) -> list[Receipt]:
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        li_rows = (
            self._db.table("line_items").select("*").in_("receipt_id", ids).execute().data
        )
        by_receipt: dict[str, list[dict]] = {}
        for li in li_rows:
            by_receipt.setdefault(li["receipt_id"], []).append(li)
        paths = [r["image_path"] for r in rows if r.get("image_path")]
        urls = signed_urls(self._db, paths)
        return [
            self._row_to_receipt(
                r, by_receipt.get(r["id"], []), urls.get(r.get("image_path"))
            )
            for r in rows
        ]

    def create_receipt(
        self,
        *,
        owner_persona_id: str,
        data: ReceiptCreate,
        image_path: str | None,
        base_currency: str | None = None,
        base_amount: float | None = None,
        fx_rate: float | None = None,
        fx_date: date | None = None,
    ) -> Receipt:
        if data.trip_id is not None:
            self.get_trip_for_persona(data.trip_id, owner_persona_id)  # visibility
        paid_by = data.paid_by_persona_id or owner_persona_id
        row = (
            self._db.table("receipts")
            .insert(
                {
                    "trip_id": data.trip_id,
                    "owner_persona_id": owner_persona_id,
                    "paid_by_persona_id": paid_by,
                    "merchant": data.merchant,
                    "purchase_date": data.purchase_date.isoformat()
                    if data.purchase_date
                    else None,
                    "currency": data.currency,
                    "subtotal": data.subtotal,
                    "tax": data.tax,
                    "tip": data.tip,
                    "total": data.total,
                    "category": data.category.value if data.category else None,
                    "payment_method": data.payment_method,
                    "image_path": image_path,
                    "raw_extraction": data.raw_extraction,
                    "confidence": {"low_confidence_fields": data.low_confidence_fields},
                    "status": "confirmed",
                    "base_currency": base_currency,
                    "base_amount": base_amount,
                    "fx_rate": fx_rate,
                    "fx_date": fx_date.isoformat() if fx_date else None,
                }
            )
            .execute()
            .data[0]
        )
        line_rows: list[dict] = []
        if data.line_items:
            line_rows = (
                self._db.table("line_items")
                .insert(
                    [
                        {
                            "receipt_id": row["id"],
                            "description": li.description,
                            "qty": li.qty,
                            "unit_price": li.unit_price,
                            "amount": li.amount,
                        }
                        for li in data.line_items
                    ]
                )
                .execute()
                .data
            )
        url = signed_url(self._db, image_path) if image_path else None
        return self._row_to_receipt(row, line_rows, url)

    def list_trip_receipts(self, trip_id: str, persona_id: str) -> list[Receipt]:
        self.get_trip_for_persona(trip_id, persona_id)  # visibility
        rows = (
            self._db.table("receipts")
            .select("*")
            .eq("trip_id", trip_id)
            .order("created_at", desc=True)
            .execute()
            .data
        )
        return self._assemble(rows)

    def list_personal_receipts(self, persona_id: str) -> list[Receipt]:
        rows = (
            self._db.table("receipts")
            .select("*")
            .is_("trip_id", "null")
            .eq("owner_persona_id", persona_id)
            .order("created_at", desc=True)
            .execute()
            .data
        )
        return self._assemble(rows)

    def get_receipt(self, receipt_id: str, persona_id: str) -> Receipt:
        if not _is_uuid(receipt_id):
            raise NotFound(receipt_id)
        rows = self._db.table("receipts").select("*").eq("id", receipt_id).execute().data
        if not rows:
            raise NotFound(receipt_id)
        row = rows[0]
        if row.get("trip_id"):
            self.get_trip_for_persona(row["trip_id"], persona_id)  # raises if not visible
        elif row["owner_persona_id"] != persona_id:
            raise Forbidden(receipt_id)
        return self._assemble([row])[0]

    def delete_receipt(self, receipt_id: str, persona_id: str) -> None:
        self.get_receipt(receipt_id, persona_id)  # visibility
        # line_items cascade via FK; the stored image is left as an orphan (v1).
        self._db.table("receipts").delete().eq("id", receipt_id).execute()

    def set_dispute(
        self, receipt_id: str, persona_id: str, reason: str | None
    ) -> Receipt:
        self.get_receipt(receipt_id, persona_id)  # enforces visibility
        self._db.table("receipts").update(
            {
                "disputed_by_persona_id": persona_id if reason else None,
                "dispute_reason": reason,
            }
        ).eq("id", receipt_id).execute()
        return self.get_receipt(receipt_id, persona_id)

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
        if not _is_uuid(persona_id):
            return None
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
        base_currency: str = "INR",
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
                    "base_currency": base_currency,
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
        if not _is_uuid(trip_id):
            raise NotFound(trip_id)
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

    def delete_trip(self, trip_id: str, persona_id: str) -> None:
        rows = (
            self._db.table("trips").select("created_by").eq("id", trip_id).execute().data
        )
        if not rows:
            raise NotFound(trip_id)
        if rows[0]["created_by"] != persona_id:
            raise Forbidden(trip_id)  # only the creator may delete
        # FK cascades remove receipts, line_items, and trip_members.
        self._db.table("trips").delete().eq("id", trip_id).execute()
