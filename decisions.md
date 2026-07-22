# Decisions

A running log of the real calls made building DocuRetrieve. Honest and specific:
what I chose, what I seriously considered, why, and what I deliberately cut.

---

## Problem choice: #3 (messy docs → structured data), framed as a family receipt ledger

- **Chose:** Problem 3, interpreted as a receipt ledger with per-trip roll-ups and natural-language query.
- **Considered:** Problem 2 (conversational agent) — genuinely fewer moving parts and cheaper to host. Problem 1 (learn-by-watching) — rejected early; the capture + generalize + replay engine is too much surface area to do *well* in 5 days.
- **Reasoning:** Problem 3 has a hard sub-problem baked in — messy receipts (bad photos, foreign currency, partial scans) — which is exactly what the rubric rewards going deep on. Problem 2 is easy to start but easy to leave shallow.
- **Cut:** #1 and #2 entirely. #2 was the close call; I traded a slightly leaner build for a problem with more depth to mine.

## Extraction: Gemini vision (image → JSON) instead of OCR + separate parser

- **Chose:** A single multimodal Gemini 2.5 Flash call that reads the receipt image and returns structured JSON.
- **Considered:** Tesseract/classical OCR then LLM/regex extraction; a document-AI SaaS (Textract/Document AI).
- **Reasoning:** Collapses two brittle subsystems into one, handles messy real-world photos far better than classical OCR, and Gemini's free tier makes it $0. SaaS doc-AI is accurate but not free.
- **Cut:** A dedicated OCR stage and any layout-analysis code.

## Datastore: Supabase Postgres (relational) over a vector DB

- **Chose:** Postgres via Supabase free tier (also gives file storage + optional auth in one service).
- **Considered:** A vector DB (semantic search over receipts); plain SQLite on disk.
- **Reasoning:** The query patterns are relational aggregates — "sum totals by category within a trip and date range" — not similarity search. I didn't want to run two datastores for a 5-day build. SQLite risks data loss on free hosts with ephemeral disks; managed Postgres avoids that. One service covers DB + image storage.
- **Cut:** Vector search. (If semantic query becomes valuable later, it's an add-on, not the spine.)

## Query: natural language → constrained SQL

- **Chose:** Translate the user's question to read-only, parameterized SQL with Gemini, run it, format the answer, and show the receipts behind it.
- **Considered:** Fixed filter UI only; a full RAG pipeline.
- **Reasoning:** NL query is the delight moment and directly serves "queryable." Generating SQL over a small known schema is reliable and traceable (we can show the rows). Guardrails keep it read-only and sandboxed.
- **Cut:** Free-form RAG — overkill for structured aggregates.

## Hosting: Render free web service

- **Chose:** Render free tier; FastAPI serves both API and the built frontend as one deploy.
- **Considered:** Hugging Face Spaces, Fly.io, Streamlit Community Cloud.
- **Reasoning:** Render is credit-card-free and closest to a "real" product deploy. Cold-start spin-down is acceptable for an eval URL. Streamlit was fastest but caps UX polish; Fly needs a card; Spaces feels more "demo" than "product."
- **Cut:** Multi-service / separate frontend deploy — kept it one process to minimize moving parts.

## Product shape: trip-first with personas (Splitwise-flavored), not a flat receipt list

- **Chose:** Trips are the primary container (a grid of albums on the home screen). You select a **persona** (no real auth) on entry; every upload maps to you. You add member personas to a trip and see only trips you created or were shared into.
- **Considered:** A single flat ledger with an optional "trip" tag on each receipt (the simpler original plan); auto-assigning receipts to trips by date range.
- **Reasoning:** Organizing by trip matches how families actually think about shared spending and gives the product real shape. Personas add "who paid what" — a genuine recurring pain — for near-zero cost since we skip real auth. Visibility is enforced server-side using the selected persona id.
- **Cut:** Real authentication (personas are trust-on-selection — fine for a family tool, documented as a limitation) and date-based auto-assignment (explicit container beats guessing).

## Containers: trips + a trip-less personal ledger (not trip-only)

- **Chose:** A receipt lives either in a trip (shared with members) or in the uploader's private personal ledger (`trip_id IS NULL`).
- **Considered:** Everything-is-a-trip with a permanent "Everyday" catch-all trip.
- **Reasoning:** Everyday household spending isn't social and shouldn't force a shared trip; a private personal ledger models that honestly. The cost is one nullable FK and one branch in the visibility rule — cheap.
- **Cut:** The forced "Everyday" trip. Two containers, one clean visibility rule.

## Splitwise depth: per-person totals, no settle-up (v1)

- **Chose:** Within a trip, break down how much each persona paid (`paid_by_persona_id`). No balances, no "who owes whom."
- **Considered:** Full settle-up math (balances, minimized transfers).
- **Reasoning:** Per-person totals deliver most of the social value for a fraction of the build and avoid a nest of edge cases (uneven splits, multi-currency settle-up) inside a 5-day window. Settle-up is a clean stretch goal that builds on the same `paid_by` field.
- **Cut:** Settle-up for v1 (documented stretch).

## Ask scope: per-container, not global (v1)

- **Chose:** The NL→SQL ask answers within the container you're in (a trip or your personal ledger). SQL is generated read-only, container-scoped, and parameterized.
- **Considered:** A single global ask across all a persona's trips.
- **Reasoning:** Per-container matches the trip-first UI and keeps the query's visibility scope trivially correct (one container id). Global ask needs cross-trip visibility joins in the query layer — worth doing, but as a stretch once the per-container path is solid and tested.
- **Cut:** Global cross-trip ask for v1 (documented stretch).

---

<!-- Add new decisions above this line as they happen. -->
