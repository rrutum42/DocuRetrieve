-- Migration 003: receipt disputes.
-- Run once in the Supabase SQL editor (idempotent).
--
-- Lets a trip member formally flag a receipt they don't trust (the social
-- defense against fabricated claims — everyone on the trip sees the original
-- image + who flagged it). disputed_by null = not disputed.

alter table receipts
    add column if not exists disputed_by_persona_id uuid
        references personas(id) on delete set null;
alter table receipts
    add column if not exists dispute_reason text;
