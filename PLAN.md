# DocuRetrieve — Build Plan

> **Problem 3:** Turn messy documents into structured, queryable data.
> **Interpretation:** A **trip-first family receipt ledger**. You organize spending into trips (like photo albums), invite the people on the trip (Splitwise-style personas), snap receipts inside a trip, and the system reads even bad phone photos into clean structured records you can *ask questions* about — with a per-person breakdown of who paid.

---

## 1. Product framing

**Who it's for:** Families / friend groups who travel together and share expenses, plus everyday household spending. Receipts pile up; nobody enters them; nobody remembers who paid for what.

**The real problem:** Receipts are the messiest "document" people own — thermal paper, faded ink, foreign languages/currencies on trips, photographed at an angle in bad light. Manual entry is the friction that kills every budgeting habit, and "who paid what on the trip" is a recurring social headache. DocuRetrieve removes both: snap → it's in the trip → ask it anything → see who paid.

**Why this scores well:** The messiness *is* the hard sub-problem the rubric rewards. Trips + personas give it a real product shape, not just a CRUD table.

---

## 2. Scope

### In (the spine we build well)
- **Persona picker** — lightweight profiles, no real auth. Select who you are; all your uploads map to you.
- **Trips as the primary container** — a grid of trips (albums) on the home screen; create a trip with name/dates/cover; **add member personas** to a trip.
- **Visibility** — you see only trips you created or were shared into; a trip-less **personal ledger** private to your persona.
- **Upload inside a container** — receipt image/PDF → Gemini → structured JSON.
- **Always-confirm review** — image + extracted fields side by side, low-confidence flagged, correct-and-confirm before save.
- **Ledger view** per container — list, filter, sort, totals.
- **Per-person totals** within a trip — how much each persona paid (no settle-up in v1).
- **Natural-language query** scoped to the current container.
- Original image stored alongside the record.

### Deliberately out (documented in decisions.md)
- Real authentication / passwords — personas are trust-on-selection.
- Settle-up math (who owes whom) — stretch goal; per-person totals ship first.
- Global cross-trip ask — stretch; ask is per-container in v1.
- Multi-currency normalization to a home currency — we store native currency; converting to one base is out.
- Mobile app, bank/email import, exports.

---

## 3. Architecture (3 moving parts)

```
Browser — persona picker · trips grid · trip/personal ledger · review · ask
        │
        ▼
FastAPI app  ── serves the built React app + JSON API
        │
        ├──►  Gemini 2.5 Flash (vision)   image/PDF → structured JSON (OCR + extraction in one call)
        │
        └──►  Supabase                    Postgres (personas, trips, receipts) + Storage (images)
```

- **Extraction and parsing are one step** — Gemini's multimodal model returns typed JSON; no separate OCR subsystem.
- **NL query** is a text-only Gemini call: question → constrained read-only SQL **scoped to the current container** → run → format answer + show the receipts behind it.
- **No auth server** — the selected persona id is the visibility key, enforced server-side on every query.

---

## 4. Data model (Postgres / Supabase)

```
personas
  id            uuid pk
  name          text            -- "Mom", "Akshit"
  color         text            -- avatar tint
  created_at    timestamptz

trips
  id            uuid pk
  name          text            -- "France 2026"
  start_date    date  null
  end_date      date  null
  cover_image   text  null      -- Storage key
  created_by    uuid fk -> personas.id
  created_at    timestamptz

trip_members
  trip_id       uuid fk -> trips.id
  persona_id    uuid fk -> personas.id
  primary key (trip_id, persona_id)

receipts
  id                uuid pk
  trip_id           uuid null fk -> trips.id   -- NULL = personal ledger
  owner_persona_id  uuid fk -> personas.id     -- whose ledger it lives in (uploader)
  paid_by_persona_id uuid fk -> personas.id    -- who paid (defaults to owner)
  merchant          text
  purchase_date     date  null
  currency          text            -- ISO 4217
  subtotal          numeric null
  tax               numeric null
  tip               numeric null
  total             numeric null
  category          text            -- groceries | dining | fuel | lodging | transport | shopping | other
  payment_method    text null
  image_path        text            -- Storage key of the original
  raw_extraction    jsonb           -- full model output, for audit/debug
  confidence        jsonb           -- per-field confidence flags
  status            text            -- 'needs_review' | 'confirmed'
  created_at        timestamptz

line_items
  id            uuid pk
  receipt_id    uuid fk -> receipts.id
  description   text
  qty           numeric null
  unit_price    numeric null
  amount        numeric null
```

**Visibility rule (enforced server-side):** persona `P` may see receipt `R` iff
`R.trip_id` ∈ { trips where `P` is `created_by` or in `trip_members` }  **OR**  (`R.trip_id IS NULL` AND `R.owner_persona_id = P`).

Relational on purpose — the query patterns are aggregates and joins ("sum totals by category / by paid_by within a trip"), not vector similarity.

---

## 5. The hard sub-problem: messy input (where we go deep)

Every one gets a defined, graceful behavior — not a crash:

| Failure mode | Behavior |
|---|---|
| Blurry / low-light photo | Extract what's readable; mark unreadable fields low-confidence; ask user to confirm the total. |
| Foreign language / currency (trips!) | Detect currency; store ISO code + original text; still categorize. |
| Not a receipt at all | Detect and reject politely — no garbage rows. |
| Partial / torn receipt | Save what exists; `status = needs_review`; never invent a total. |
| Multiple receipts in one photo | v1: detect and ask for one at a time (documented limitation). |
| Malformed model JSON | Schema-validate; one bounded retry; then fall back to review with raw text shown. |
| Gemini rate limit / timeout | Queue + friendly retry; the upload never silently disappears. |

**Design principle:** the model proposes, the human confirms. We never write a confident-looking number we're unsure of.

---

## 6. UX journey (sweat the end-to-end)

1. **Persona picker** — first screen, Netflix-style. Pick or create a profile. (Seeded sample personas so it's not empty.)
2. **Home** — two zones: a **trips grid** (albums, with cover + total + member avatars) and **My Everyday** (your private ledger). "New trip" tile.
3. **Create trip** — name, dates, cover, add member personas.
4. **Inside a trip** — ledger of its receipts, **per-person "who paid" strip**, ask box pinned on top, upload button.
5. **Upload → review card** — original image left, extracted fields right; low-confidence highlighted; set category + `paid_by`; Confirm.
6. **Ask** — "how much on dining in France?" → number + the receipts behind it, scoped to this container.
7. **Error moments** — every failure has a human message and a next action, never a stack trace.

---

## 7. Tech stack (all $0)

- **Backend:** FastAPI (Python 3.14), Uvicorn.
- **Frontend:** React (Vite), built to static and served by FastAPI (single deploy).
- **Extraction/query:** Gemini 2.5 Flash, free tier.
- **DB + storage:** Supabase free tier (Postgres + Storage).
- **Host:** Render free web service.
- **Config:** env vars — `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`.

---

## 8. Testing strategy (tests that catch real problems)

- **Extraction contract tests:** fixture images (clean, blurry, foreign-currency, non-receipt) → parsed JSON validates against schema; non-receipt is rejected.
- **Visibility tests:** persona A cannot see persona B's private ledger or a trip A isn't in — asserted at the query layer.
- **NL→SQL guardrails:** generated SQL is read-only, container-scoped, parameterized; a hostile question can't escape the sandbox or cross containers.
- **Per-person totals:** seed known receipts with varied `paid_by` → assert the breakdown is exact.
- **API happy path + fallback:** upload → review → confirm → ask; plus the malformed-JSON fallback path.

Mock Gemini in unit tests (recorded response fixtures) so tests run offline and free.

---

## 9. Deployment

- Supabase project (DB + storage bucket) — free, no card.
- Render web service from GitHub — free, no card. Build: install deps + build React; Start: uvicorn.
- Env vars in Render dashboard.
- One-shot local setup in README (`.env.example`, `uv sync`, build frontend, `uvicorn`).

---

## 10. 5-day milestones

- **Day 1:** Git + repo skeleton, FastAPI, Supabase schema (personas/trips/members/receipts/line_items), Gemini extraction module + schema validation. One image → validated record.
- **Day 2:** Persona picker + home (trips grid + Everyday) + create-trip/add-members. Visibility rule enforced.
- **Day 3:** Upload + always-confirm review card + image storage; ledger view with filter/sort/totals.
- **Day 4:** Per-person "who paid" breakdown; NL→SQL ask (container-scoped) with guardrails and traceable answers.
- **Day 5:** Messy-input hardening (failure table), tests, empty/error states, `decisions.md`, README, deploy, polish.

---

## 11. Settled decisions

- React (Vite) frontend; no real auth (personas). ✓
- Trips are the primary container; a trip-less personal ledger exists alongside. ✓
- Splitwise depth = per-person totals, no settle-up (settle-up = stretch). ✓
- Ask is per-container in v1 (global = stretch). ✓
- Always-confirm review before any save. ✓
