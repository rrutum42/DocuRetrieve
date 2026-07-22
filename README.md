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
# 1. Install backend dependencies (into .venv)
uv pip install -e ".[dev]"

# 2. Configure (optional for a first look — see stub note below)
cp .env.example .env
#   fill in GEMINI_API_KEY, and SUPABASE_URL + SUPABASE_KEY
#   IMPORTANT: SUPABASE_URL is the project API URL — https://<ref>.supabase.co —
#   NOT the dashboard URL (https://supabase.com/dashboard/project/<ref>).

# 3. Build the frontend (FastAPI serves it in one process)
cd frontend && npm install && npm run build && cd ..

# 4. Run the app (serves API + the built UI)
uv run uvicorn app.main:app --reload

# 5. Run the backend tests
uv run pytest
```

Open **http://127.0.0.1:8000** for the app. `/api/health` and `/api/config`
show status; `/docs` is the interactive API playground.

### Frontend dev with hot reload

For UI work, run the Vite dev server alongside the API (it proxies `/api` to
port 8000, so no CORS fuss):

```bash
uv run uvicorn app.main:app --reload      # terminal 1 — API on :8000
cd frontend && npm run dev                 # terminal 2 — UI on :5173
```

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

- **Day 1 ✓** — extraction spine (image → structured JSON), schema, bounded
  retry + safe fallback, offline tests.
- **Day 2 ✓** — persona picker, trips home (grid + personal "Everyday"),
  create-trip + share-with-people, and the **server-side visibility rule**
  (a persona sees only trips they created or were shared into).
- **Day 3 ✓** — receipt **upload → always-confirm review → save** into a trip or
  the personal ledger, with the original image stored in a **private** Supabase
  bucket (served via short-lived signed URLs). Ledger view with per-currency
  totals, category filter, and sort. 30 backend tests passing.

Next: per-person "who paid" totals and the natural-language ask box
(see `PLAN.md` §10, Day 4).

## License

Source-available under the **[PolyForm Noncommercial License 1.0.0](./LICENSE.md)**.
You may use, modify, and share this project for any **noncommercial** purpose
(personal, research, education, nonprofit). Using it for commercial advantage,
revenue generation, or enterprise/business purposes is **not** permitted.
© 2026 Rrutum Lavana.
