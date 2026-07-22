-- DocuRetrieve schema (Postgres / Supabase)
-- Run once in the Supabase SQL editor.
--
-- Note on security model: personas are app-level profiles, NOT Supabase auth
-- users (there is no real auth by design). The visibility rule is therefore
-- enforced in the application layer, not via RLS + auth.uid(). See PLAN.md §4.

create extension if not exists "pgcrypto";  -- for gen_random_uuid()

-- Profiles you can "log in" as. No passwords by design.
create table if not exists personas (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    color       text,                       -- avatar tint
    created_at  timestamptz not null default now()
);

-- The primary container: a trip (album). Everyday spending lives OUTSIDE any
-- trip, in the uploader's personal ledger (receipts.trip_id is null).
create table if not exists trips (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    start_date  date,
    end_date    date,
    cover_image text,                        -- Storage key
    created_by  uuid not null references personas(id) on delete cascade,
    created_at  timestamptz not null default now()
);

-- Who can see / participate in a trip (Splitwise-style membership).
create table if not exists trip_members (
    trip_id     uuid not null references trips(id) on delete cascade,
    persona_id  uuid not null references personas(id) on delete cascade,
    primary key (trip_id, persona_id)
);

create table if not exists receipts (
    id                 uuid primary key default gen_random_uuid(),
    trip_id            uuid references trips(id) on delete cascade,        -- null = personal ledger
    owner_persona_id   uuid not null references personas(id) on delete cascade,  -- uploader / ledger owner
    paid_by_persona_id uuid not null references personas(id) on delete cascade,  -- who paid (per-person totals)
    merchant           text,
    purchase_date      date,
    currency           text,                 -- ISO 4217
    subtotal           numeric,
    tax                numeric,
    tip                numeric,
    total              numeric,
    category           text,                 -- groceries|dining|fuel|lodging|transport|shopping|other
    payment_method     text,
    image_path         text,                 -- Storage key of the original
    raw_extraction     jsonb,                -- full model output (audit/debug)
    confidence         jsonb,                -- low-confidence field flags
    status             text not null default 'needs_review',  -- 'needs_review' | 'confirmed'
    created_at         timestamptz not null default now()
);

create table if not exists line_items (
    id          uuid primary key default gen_random_uuid(),
    receipt_id  uuid not null references receipts(id) on delete cascade,
    description text,
    qty         numeric,
    unit_price  numeric,
    amount      numeric
);

-- Indexes for the query patterns we actually run.
create index if not exists idx_receipts_trip        on receipts(trip_id);
create index if not exists idx_receipts_owner        on receipts(owner_persona_id);
create index if not exists idx_receipts_paid_by      on receipts(paid_by_persona_id);
create index if not exists idx_receipts_category     on receipts(category);
create index if not exists idx_receipts_date         on receipts(purchase_date);
create index if not exists idx_trip_members_persona  on trip_members(persona_id);
create index if not exists idx_line_items_receipt    on line_items(receipt_id);

-- Visibility (enforced in app, documented here):
--   persona P sees receipt R iff
--     R.trip_id in (select trip_id from trip_members where persona_id = P
--                   union select id from trips where created_by = P)
--     OR (R.trip_id is null and R.owner_persona_id = P)
