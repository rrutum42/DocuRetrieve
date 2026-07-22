-- Migration 002: multi-currency support.
-- Run once in the Supabase SQL editor (idempotent).
--
-- Adds a per-trip base currency and a per-receipt conversion snapshot
-- (home-currency amount + the rate and date it was locked at). The native
-- currency/total columns are unchanged and remain the source of truth.

alter table trips
    add column if not exists base_currency text not null default 'INR';

alter table receipts
    add column if not exists base_currency text;   -- target currency of the snapshot
alter table receipts
    add column if not exists base_amount   numeric; -- total converted to base_currency
alter table receipts
    add column if not exists fx_rate       numeric; -- rate used (native -> base)
alter table receipts
    add column if not exists fx_date        date;   -- date whose rate was applied
