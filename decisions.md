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

## Model pin: `gemini-flash-latest` alias, not a version-numbered flash

- **Chose:** `gemini-flash-latest` as the default extraction model.
- **Considered:** Pinning a specific version (`gemini-2.5-flash`, `gemini-3.6-flash`).
- **Reasoning:** On first live test, `gemini-2.5-flash` returned 404 "no longer available to new users" — Google retires numbered flash models on a rolling basis. For a $0 project meant to keep working unattended, the stable `-latest` alias avoids silent breakage when a version is sunset. The graceful-fallback path caught the 404 cleanly (upload wasn't dropped), which validated that error handling — but a working default matters more.
- **Tradeoff accepted:** `-latest` can shift extraction behavior when Google rolls the alias forward. Acceptable here; if outputs ever drift, pin the then-current version. `GEMINI_MODEL` is env-overridable for exactly this.
- **Cut:** Version pinning for v1.

## Multi-currency: store native + snapshot-convert at save time, per-trip base currency

- **Chose:** Each receipt keeps its **native** currency/total as the source of truth, plus a **conversion snapshot** (`base_amount`, `fx_rate`, `fx_date`) taken **once at save time** using the historical rate for the receipt's own date. Each trip has a single `base_currency` (chosen at creation, default INR); the personal ledger uses the app default. FX source is **Frankfurter** (ECB daily rates — free, no API key).
- **Considered:** (a) Overwriting the amount with the converted value (the user's first phrasing); (b) converting live on every ledger load; (c) per-persona home currency so each viewer sees their own; (d) a paid FX API.
- **Reasoning:**
  - *Never lose the printed amount* — overwriting kills auditability and breaks if the base currency changes later or a rate was wrong. Native stays immutable.
  - *Snapshot beats live* — the number is reproducible (won't silently shift), fast (no per-row API calls), and resilient (a later FX outage doesn't break display). "Converted at the purchase-date rate" is an explainable figure.
  - *Per-trip base currency* is the simplest model that answers "what did this trip cost us at home?" Per-persona currency was deferred — it needs multiple snapshots or live conversion for marginal benefit in a family tool.
  - *Frankfurter* fits the $0 constraint and covers the ~30 major currencies a traveling family uses (incl. INR); verified live for historical dates.
- **Real-world handling (non-fatal):** same currency → rate 1, no call; unsupported currency / FX down / missing date → save the **native amount only**, mark **"not converted"**, surface it in the ledger, allow later backfill. A conversion failure never blocks a save.
- **Cut:** live conversion, per-persona currency, and converting subtotal/tax/tip (only the total — the roll-up figure — is converted in v1).

## Ask box: NL → validated query spec → Python execution (not NL → SQL)

- **Chose:** The model compiles a question into a small **validated `QuerySpec`** (operation + filters), which we execute **in Python over the container's already-loaded receipts**. Answers return the exact matching receipts as evidence.
- **Considered:** (a) the original plan's **NL → raw SQL**; (b) feeding all receipts to the model and letting it answer directly (LLM does the math).
- **Reasoning:**
  - *No SQL execution path* — Supabase's REST client can't run arbitrary SQL, and we have no direct DB connection (only the API key). NL→SQL would need infrastructure we deliberately don't run.
  - *Injection-proof* — a structured spec validated by Pydantic has no injection surface; generated SQL does.
  - *Exact arithmetic* — Python sums/averages are deterministic; letting the LLM do math invites hallucinated totals.
  - *Traceable* — because we filter receipts ourselves, we return the precise set behind each answer, and the UI filters the ledger to them.
  - The model call sits behind an `AskPlanner` seam, so the whole feature is unit-tested without Gemini; a no-LLM fallback lists everything.
- **Real-world handling:** planner errors fall back to a "list" spec (never fail the question); unconverted receipts are excluded from sums with an explicit note; unknown payer/category yields an honest "no receipts found".
- **Cut:** NL→SQL, LLM-does-the-math, and a "group by person" operation (the per-person "who paid" strip already answers that visually).

## Depth: independently validate the model's output, and measure it

- **Chose:** After the model extracts a receipt, run an independent **validation
  layer** that (a) checks arithmetic (subtotal+tax+tip==total, line-item sums),
  (b) **safely self-corrects** by deriving only *blank* fields via algebra, and
  (c) flags sanity problems (future dates, unknown currency, non-positive total).
  Then **measure** the validator with an eval harness (precision/recall on a
  labeled set), gated in CI.
- **Considered:** (a) trusting the model's own `low_confidence_fields` and moving
  on — the common approach; (b) auto-repairing *all* inconsistent fields; (c) a
  second LLM "verify" pass.
- **Reasoning:**
  - Trusting self-report is exactly what most receipt tools do, and it's where
    they quietly fail — an LLM will confidently hand back numbers that don't add
    up. Independent, deterministic checks catch what self-report misses at zero
    marginal cost.
  - **Derive-blank-but-never-overwrite** keeps the "model proposes, human
    confirms" principle intact: we only fill gaps we can prove algebraically, and
    surface real conflicts for review rather than papering over them.
  - A second LLM pass costs tokens/latency and can hallucinate agreement; simple
    arithmetic is exact and free.
  - **Measuring** it (eval harness + CI gate) is the point of the depth: the
    take-home asks us to solve the hard part *well*, and "I measured the validator
    at 100% precision/recall on a labeled set, and it guards every commit" is
    evidence, not a claim.
- **Cut (for now):** full extraction-accuracy eval on real receipt images (needs
  a hand-labeled image corpus — planned, see evals/README.md), and the second-LLM
  verification pass.

---

<!-- Add new decisions above this line as they happen. -->
