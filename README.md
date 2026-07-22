# DocuRetrieve

Turn messy receipts into clean, queryable data — organized by **trip**, shared
with the **people** on it, and answerable in plain English.

Snap a receipt (even a bad phone photo, even in another currency), and Gemini's
vision model reads it into a structured record. Everything lives inside a trip
(like a photo album) or your private everyday ledger, with a per-person "who
paid" breakdown and a natural-language ask box.

> Problem 3 of the take-home: *turn messy documents into structured, queryable
> data.* See [`PLAN.md`](./PLAN.md) for scope and [`decisions.md`](./decisions.md)
> for the reasoning behind every call.

## Stack (all $0)

- **FastAPI** (Python 3.14) — API + serves the built frontend as one deploy
- **Gemini 2.5 Flash** — image/PDF → structured JSON in a single call (no separate OCR)
- **Supabase** — Postgres + file storage (free tier)
- **React (Vite)** frontend
- **Render** free web service for hosting

## Run it locally

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
# 1. Install dependencies (into .venv)
uv pip install -e ".[dev]"

# 2. Configure (optional for a first look — see stub note below)
cp .env.example .env
#   fill in GEMINI_API_KEY, SUPABASE_URL, SUPABASE_KEY

# 3. Run the API
uv run uvicorn app.main:app --reload

# 4. Run the tests
uv run pytest
```

Open http://127.0.0.1:8000/api/health to confirm it's up, and
http://127.0.0.1:8000/api/config to see what's wired.

### No API key yet? Use the stub

The extraction pipeline has a `generate` seam. With no `GEMINI_API_KEY` (or
`DOCURETRIEVE_USE_STUB=true`), `/api/extract` returns a deterministic stubbed
receipt so you can exercise the app end to end without a key. The tests use the
same seam with recorded fixtures, so `pytest` runs fully offline.

## Database

Run [`db/schema.sql`](./db/schema.sql) once in the Supabase SQL editor to create
the `personas`, `trips`, `trip_members`, `receipts`, and `line_items` tables.

## Project layout

```
app/
  config.py       env-driven settings
  schemas.py      Pydantic contract (extraction schema)
  extraction.py   Gemini call + validation + bounded retry + safe fallback
  db.py           Supabase client
  main.py         FastAPI app (health, config, /api/extract)
db/schema.sql     Postgres schema
tests/            offline extraction tests (fixture-backed)
frontend/         React app (added Day 2)
```

## Status

Day 1 complete: extraction spine + schema + tests. Persona/trip endpoints,
review UI, ledger, per-person totals, and the ask box follow (see `PLAN.md` §10).
