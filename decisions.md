# Decisions

A running log of the real calls made building DocuRetriever. Honest and specific:
what I chose, what I seriously considered, why, and what I deliberately cut.

---

## Why this problem (motivation)

- **Personal resonance, not a random pick.** I'm about to go on a family trip, and
  splitting and tracking group expenses is a problem I actually live — messy
  receipts, "who paid for what", "what did this cost us at home". I chose this
  topic because I wanted to build something I'd genuinely use, so the design
  decisions came from real friction rather than a spec on paper.
- **What I chose to go deep on, in priority order:**
  1. **Parsing receipts** — the hard, messy core: bad photos, handwriting,
     foreign currency, non-receipts. This is where I spent the most effort and
     where I built independent validation + a measured eval.
  2. **UX around the user journey** — trip-first organization, personas, review-
     before-save, traceable answers, graceful failures. The product should feel
     like a real tool, not a demo.
  3. **Running everything free of cost** — the entire system ($0 host, free DB,
     Gemini free tier) so it can live on unattended without a bill. This
     constraint shaped the stack throughout.
- **Honest about where it's weakest — the NL queries.** The natural-language ask
  is the piece that **still needs a lot of work**. The eval passes on the intended
  question shapes (25/25 on a small synthetic set), but that's not the same as
  robustness: real-world phrasing variety, multi-currency nuance, cross-trip
  questions, and a larger labeled set are all still open. I'm treating the current
  state as a solid, honestly-measured foundation — not a finished feature. See
  "Ask, part 2" below and the honesty notes in `evals/RESULTS.md`.

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

## Save gate: a receipt must have a total > 0 (blocks zero-cost rows & non-receipts)

- **Chose:** Reject saving a receipt whose total is missing or ≤ 0, enforced
  **server-side** (422) with a matching client-side guard (the "Confirm & save"
  button is disabled with a "discard if this isn't a receipt" hint).
- **Considered:** relying solely on the model's `is_receipt` flag to keep
  non-receipts out; allowing zero-total rows and filtering them later.
- **Reasoning:** Two real gaps shared one fix. (1) `is_receipt` classification
  is excellent but not guaranteed every run — a misread non-receipt (e.g. a koi-
  pond photo) shouldn't be persistable. (2) The app previously accepted a
  zero-cost receipt outright. A "total > 0" invariant closes both: a non-receipt
  has no real total, and a zero-cost row is meaningless in a ledger. The server
  is the enforcement point (defense in depth); the client guard is UX.
- **Scope:** total is the hard gate; currency is NOT required at save (the
  validation layer already flags a missing currency, and FX conversion degrades
  gracefully) — keeping the gate focused avoids over-blocking legitimate saves.

## Fabricated receipts: flag + social dispute, not a "fraud detector"

- **Threat:** in a trip with settle-up, a member has motive to fake a receipt
  (photograph "₹5000" written on paper) to inflate what they "paid" so others
  owe more. The `total > 0` gate doesn't catch this — a fake has a number.
- **Chose:** a two-layer, honest defense. (1) A **completeness/authenticity
  signal** in the validation layer: a genuine issued receipt shows several of
  {merchant, date, itemized lines, tax/subtotal}; a bare amount shows almost
  none, so it's **flagged** ("looks unusually sparse — verify it's genuine") in
  the review card and ledger. (2) A **member dispute** action: any trip member
  who can see a receipt can flag it with a reason; it shows a 🚩 badge + banner
  to everyone on the trip, and can be resolved.
- **Considered / rejected:** blocking sparse receipts (our own eval proved legit
  receipts are often handwritten/minimal — the hospital list, the college slip —
  so blocking would reject real ones); an ML "is this fake" classifier as a hard
  gate (no image-only system reliably detects a well-made fake — overselling it
  would be dishonest).
- **Reasoning:** the real defense in a *shared* ledger is **transparency**, and
  it's already 90% there — every receipt is shared with members, shows the
  original image, and is attributed to a persona. Formalizing that with a flag +
  dispute matches how Splitwise-style trust actually works: people who can see
  the evidence hold each other accountable. The completeness signal simply makes
  the suspicious ones easy to spot.
- **Stated limit (in README/here):** this is not fraud-proof. If the model both
  misclassifies a fake as a receipt AND it carries enough fabricated structure,
  it can still be saved — the human review + member visibility are the backstop,
  not a guarantee. Honesty about this boundary is the right engineering posture.
- **Cut:** hard blocking, and an automated authenticity classifier as a gate.

## Deploy: one Docker image on Render, not the native Python runtime

- **Chose:** A multi-stage Dockerfile (Node builds the React frontend → Python
  runs FastAPI and serves that build) deployed via a `render.yaml` blueprint as a
  single free web service.
- **Considered:** (a) Render's native Python runtime with a build command;
  (b) two services — a static site for the frontend + a web service for the API.
- **Reasoning:**
  - The app is deliberately *one process serving both* API and frontend. Render's
    native Python runtime doesn't reliably provide Node to build the React app,
    so a single-language runtime can't produce the bundle. Docker gives us both
    toolchains cleanly and makes the build reproducible locally (`docker build`).
  - Two services would split the deploy, add CORS/config surface, and contradict
    the single-deploy design. Not worth it for a free-tier project.
  - Deps are installed from `requirements.txt` (mirroring pyproject) rather than
    `pip install .`, so the app is NOT installed as a package — `app/` and
    `frontend/dist/` stay siblings, which is what `main.py` relies on to locate
    the built frontend.
  - Secrets (`GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`) are `sync:false` in
    the blueprint — set in the dashboard, never committed. `.dockerignore` keeps
    `.env` and the private receipt images out of the image.
- **Cut:** native-runtime deploy and the split frontend/backend hosting.

## Ask: a `breakdown` operation, not free-form SQL

- **Chose:** Extend the QuerySpec with a single new operation, `breakdown`, plus a
  `group_by` dimension (`category | paid_by | currency | merchant`). The executor
  filters as usual, then groups the matched receipts and sums `base_amount` per
  group, returning sorted `BreakdownRow`s alongside the grand total.
- **Problem it fixes:** the query language only had scalar aggregations, so
  "how much did *each person* spend?" or "*by category*" had no valid target —
  the planner was forced into `sum` (one number) or `list` (flat dump), which
  reads as a wrong/unhelpful answer. Grouping was the missing primitive.
- **Reasoning:**
  - Stays inside the safe design: the model still only emits a validated spec, and
    a deterministic Python executor does the arithmetic. No SQL, no injection
    surface, exact numbers, every row still traceable to its receipts (`matched`).
  - Composes with existing filters for free — "break down *dining* by person" is
    `operation=breakdown, group_by=paid_by, category=dining`. No new filter code.
  - Added worked question→spec examples to the planner prompt (few-shot). The
    zero-shot prompt on the weak `flash-lite` planner was drifting on paraphrases;
    examples disambiguate breakdown-vs-sum and the common phrasings.
- **Honesty:** rows without a converted `base_amount` count toward a group's
  tally but not its sum (same rule as the scalar sum path). The executor is
  CI-gated (`tests/test_ask.py`, `tests/test_ask_eval.py`); the live planner
  mapping for these new question shapes still needs a keyed `evals.ask_eval` run
  to score — the committed live numbers predate this change.
- **Cut:** multi-dimension grouping (group by person *and* category at once),
  top-N, and cross-group comparison sentences — a single dimension covers the
  common questions; the rest can follow if asked for.

## Ask, part 2: the query language that real questions actually need

- **Trigger:** ran the *live* planner over ~25 realistic paraphrases (not just the
  friendly dataset phrasings) and watched where the answers were wrong. The
  planner's *operation classification* was fine even on slang ("petrol/gas" →
  `fuel`, "eating out" → `dining`); every failure was the **query language being
  too narrow to express the question**. Concretely:
  - "did we spend more on dining **or** fuel?" / "who spent more, Mom or Dad?" /
    "how much **more** did Mom pay than Dad?" → collapsed to a whole-dimension
    `breakdown` that never actually compares the two named things.
  - "what are our **3 biggest** expenses?" → `max`, which returns exactly **one**.
  - "receipts **most to least** expensive" → an unordered `list` printing just a
    count, no amounts.
  - "what **percent** did Dad cover?" → a breakdown with no share figure.
  - "what's the **weather**?" → forced onto some arbitrary `sum`.
- **Chose:** extend the same validated-spec / deterministic-executor design (no
  SQL, still injection-proof, still traceable) with four bounded additions:
  1. **`compare`** — `group_by` + `compare_subjects` (the named labels). Executor
     sums each subject, sorts, and reports the leader and the **gap** (`value` =
     difference between the top two, so it's checkable). A named subject with no
     receipts is a real 0; equal totals answer "it's a tie". Empty subjects →
     compare the top two automatically.
  2. **`list` gains `sort` + `limit`** (`amount_desc|amount_asc|date_desc|date_asc`,
     top-N). "3 biggest expenses" → `list, sort=amount_desc, limit=3`; the answer
     now itemises the rows (merchant + amount) instead of just counting.
  3. **`share` on `BreakdownRow`** — each group's percent of the breakdown total,
     surfaced in the sentence and the UI, so "what percent did X cover" / "what
     fraction was food" are answerable as a breakdown.
  4. **`unsupported`** — an explicit honest-refusal operation for off-ledger
     questions, instead of fabricating a number (golden rule 6).
- **Reasoning:** each is one primitive the earlier design explicitly *cut*, added
  the same way — the model only emits a validated `QuerySpec`, Python does all the
  arithmetic, every answer still carries its `matched` evidence. New fields are
  additive/optional, so the 18 existing cases and their specs are untouched.
- **Kept the planner model** at `flash-lite`: the diagnostic showed classification
  wasn't the bottleneck, so the cheaper, separate quota bucket (per the extraction
  vs. ask split) still holds. The prompt gained the new operations, the
  sort/limit/compare fields, and worked examples for each.
- **Honesty:** the executor gate grew to **25 cases** and is green in CI
  (`tests/test_ask.py`, `tests/test_ask_eval.py`), including the tie, the
  zero-receipt subject, and the top-N ordering. The **live planner was re-scored
  end-to-end: 25/25 operation and 25/25 answer accuracy** (`evals/RESULTS.md`).
  The first live run was 24/25 — "what percent did Mom pay?" also set
  `paid_by=Mom`, collapsing the breakdown's denominator; a prompt rule
  (percentage questions don't filter to the subject) fixed it to 25/25. Logged
  because that's the failure the eval exists to catch.
- **Still cut:** multi-dimension grouping (person × category at once) and
  arithmetic across more than two compare subjects beyond a simple ranking.

## Duplicate receipts: reject an exact match in a trip, with a human override

- **Problem:** the same receipt lands in a trip twice — someone taps save twice,
  or two people photograph the same shared dinner bill. That silently
  double-counts the trip's spend and every settle-up balance derived from it,
  and nothing else catches it (the `total > 0` gate and the completeness signal
  both pass — it's a real receipt, just entered twice).
- **Chose:** reject a save that *exactly* matches a receipt already in the trip on
  the four fields that identify a transaction — **merchant + purchase_date +
  total + currency** — with an HTTP **409** and an actionable message. Enforced
  **server-side** (a direct POST can't bypass it), scoped **per-trip** (the same
  bill in a different trip is legitimate), and skipped for the personal ledger.
  The match logic is a pure function (`app/dedupe.py`), unit-tested independently.
- **Human override (`allow_duplicate`):** the match is deliberately strict, but a
  genuine repeat purchase (same shop, same day, same price) can happen. Rather
  than a dead end, the review card catches the 409 and offers **"Save anyway"**,
  which resubmits with `allow_duplicate=true`. Keeps the invariant "the model
  proposes, a human confirms" and "degrade gracefully, never block the action".
- **Why strict/exact, not fuzzy:** a looser match (e.g. merchant + date only, or
  a fuzzy amount) would block distinct purchases — two coffees at the same café,
  or a second fuel stop — which is worse than the occasional missed near-dup.
  Exact-on-four-fields is a high-precision "same receipt twice" signal; the
  override covers the rare true repeat. A missing key field (no merchant/date/
  total/currency) is never treated as a duplicate — we don't block on weak data.
- **Cut:** fuzzy/near-duplicate detection (image hashing, amount tolerance,
  same-merchant-same-day heuristics) and dedup across the personal ledger — the
  request was per-trip, and exact-match + override covers the real mistake
  without false positives.

## Ask, part 3: a conversation, not one-shot questions (context-carry)

- **Want:** let people explore — "how much did Bob pay?" → "and on dining?" →
  "what about groceries?" — instead of re-typing the full question each time.
- **Tension:** the whole ask design's strength is that each question compiles to a
  *stateless, validated `QuerySpec`* a deterministic executor runs (injection-
  proof, exact, traceable). A stateful conversational agent would trade all of
  that away.
- **Chose (context-carry planner):** keep the executor and the QuerySpec exactly
  as-is. Only the *planner* becomes context-aware — the client sends the recent
  turns (`history: [{question, answer}]`) with each question, and the planner
  resolves a follow-up fragment into a COMPLETE spec: inherit the still-relevant
  filters from the previous question, apply the change. A self-contained question
  ignores the history. Verified live: "and on dining?" kept `paid_by=Bob` and
  added `category=dining`; "what about groceries?" kept Bob and swapped the
  category. No shared mutable state; every answer is still a fresh, exact run.
- **History lives in the session, not the DB:** the thread is React state +
  `sessionStorage`, keyed per container (`ask.trip.<id>` / `ask.personal`), so it
  survives navigation within a visit, never leaks one trip's conversation into
  another, and adds no schema/migration or privacy surface. Server-side the
  `history` list is length-capped (12) and each turn's strings are bounded, and
  the planner only renders the last 6 turns — so a long thread can't blow up the
  prompt (or the free-tier token budget).
- **Testable seam kept:** prompt assembly is a pure `build_planner_prompt(context)`
  so the history rendering (present/absent, bounded) is unit-tested without
  Gemini; an endpoint test asserts the turns actually reach the planner.
- **Cut:** a full conversational agent (state + tool-chaining) and DB-persisted,
  cross-member chat threads — both give up guarantees or add surface for a
  feature the context-carry approach already delivers.

## Ask: query disputes; optimistic chat send

- **Disputes are queryable now.** A trip member can flag a receipt as disputed
  (`disputed_by_persona_id` + `dispute_reason`), but the ask couldn't see it.
  Added a `disputed: bool | None` filter to `QuerySpec` that composes with the
  existing operations — "which receipts are disputed?" (list), "how many
  disputes?" (count), "how much is disputed?" (sum). Same validated-spec /
  deterministic-executor design; a disputed-receipts list also surfaces the
  reason so it's actually useful. Executor gate +1 case (27); verified live
  against the real trip's flagged receipt.
- **Chat send is optimistic.** The question now appears in the thread the instant
  you press Enter (rendered with a "Thinking…" placeholder), and the answer fills
  in when the planner returns — instead of the whole turn waiting on the round
  trip. Errors land in the thread in place of the pending answer. Pending turns
  aren't persisted to sessionStorage. Verified: at 150 ms post-Enter the question
  is on screen, input cleared, answer not yet arrived.

---

<!-- Add new decisions above this line as they happen. -->
