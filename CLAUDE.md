# Working on DocuRetriever

Project instructions for anyone (human or AI) changing this codebase. These are
the conventions the project already follows — match them.

DocuRetriever turns messy receipt photos into clean, queryable, trip-organized
data. Backend: FastAPI + Gemini (vision + text) + Supabase. Frontend: React
(Vite), served by FastAPI as one deploy. See `README.md`, `PLAN.md`, and
`decisions.md` (the running log of real trade-offs — keep it current).

## Golden rules

1. **Every change updates its tests.** Add or adjust tests in the same change,
   never "later". A change isn't done until `uv run pytest` is green and, for
   frontend changes, `cd frontend && npm run build` succeeds.
2. **Small, incremental, self-contained changes.** One concern per change. Don't
   bundle a refactor with a feature. Keep the tree runnable at every step.
3. **Server is the source of truth.** Never trust the client for visibility,
   validation, or auth. Enforce rules in the API layer even if the UI also does.
4. **The model proposes, a human confirms.** Never silently persist model output
   as fact — surface it for review, flag what's uncertain, correct only what's
   provably safe (see `app/validation.py`).
5. **Degrade gracefully, never crash the user's action.** Classify failures
   (e.g. `rate_limited`) and return an actionable message; keep a manual path.
6. **Be honest about limits.** If a change bounds coverage or can't fully solve
   something, say so — in `decisions.md`, the UI, and/or `evals/RESULTS.md`.

## Architecture: seams for testability

The expensive/external pieces sit behind interfaces so the whole app is testable
offline with no API keys or network:

- **Repository** (`app/repository.py`) — `InMemoryRepository` (tests / no-DB dev)
  and `SupabaseRepository` (live) implement the same `Repository` Protocol. The
  visibility rule lives here, in one place.
- **Storage / FX / AskPlanner / extraction `generate`** — each has a live impl
  and a no-op/stub, injected via `app/deps.py` (FastAPI `Depends`) or a function
  seam. Tests inject fakes; `app.dependency_overrides` swaps them at the HTTP
  layer.

When you add an external dependency, add it behind a seam the same way, with a
fake for tests. Never make a test require the network or a real key.

## Testing

- Run: `uv run pytest` (fast, fully offline — Gemini/Supabase/FX are all faked).
- Cover the **security-critical** paths explicitly: visibility (a persona can't
  see/modify another's data), server-side validation, injection-proof queries.
- Two eval harnesses gate quality in CI — keep them green:
  - `tests/test_validator_eval.py` (validation precision/recall)
  - `tests/test_ask_eval.py` (NL query → correct answer, all cases)
- The live evals (`python -m evals.extraction_eval`, `evals.ask_eval`) measure
  the model itself; run them when you touch extraction or the ask pipeline, and
  update `evals/RESULTS.md` honestly (don't inflate numbers).

## Code style

**Python**
- `from __future__ import annotations`; modern type hints (`str | None`).
- Pydantic models are the contracts between model ↔ API ↔ DB (`app/schemas.py`,
  `app/api_models.py`). Validate at the boundary.
- Prefer small **pure functions** for logic (see `app/summary.py`,
  `app/validation.py`, `app/ask.py`) — they're trivially testable.
- Comments explain **why**, not what. Match the surrounding density.
- Keep routers thin; put logic in the repository / pure modules.

**React / JS**
- Functional components + hooks. **No TypeScript** (plain `.jsx`).
- Plain CSS in `frontend/src/styles.css` using the design tokens (`--accent`,
  `--ink`, `--line`, radii). No CSS framework. Style both the shape and the
  states (loading, empty, error).
- API access goes through `frontend/src/api.js`; it sends the acting persona via
  the `X-Persona-Id` header. Don't call `fetch` ad hoc.
- Reuse the shared components (`Loader`, `ConfirmModal`, `FreeTierNote`, covers)
  rather than re-implementing.

## Product invariants (don't regress these)

- **Money:** a receipt's native currency/amount is immutable source of truth.
  Conversions are a snapshot (`base_amount`/`fx_rate`/`fx_date`) taken at save
  time; never overwrite the printed amount.
- **A receipt needs a total > 0 to save** (blocks zero-cost rows and non-receipts).
- **Visibility:** a persona sees a trip only if they created it or are a member;
  a personal-ledger receipt only if they own it. Strangers get 404 (don't leak
  existence).
- **Anti-fabrication:** sparse receipts are *flagged* (never blocked), and trip
  members can dispute. It's a signal + social defense, not a fraud "proof".

## Privacy & secrets (hard rules)

- **Never commit** real receipt images, real labels/predictions, or `.env`. These
  are gitignored (`evals/fixtures/images/`, `labels.json`, `predictions.json`).
  Only synthetic fixtures and aggregate results are tracked.
- Before any commit, sanity-check the staged set for those paths.
- Secrets come from env vars (`GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`) —
  in `.env` locally, in the host dashboard in prod. `render.yaml` marks them
  `sync:false`.

## Common commands

```bash
uv run pytest                                   # backend tests (offline)
uv run uvicorn app.main:app --reload            # API on :8000 (serves built UI)
cd frontend && npm run dev                      # UI dev server on :5173
cd frontend && npm run build                    # build the frontend (must pass)
python -m evals.validator_eval                  # validation eval
python -m evals.ask_eval predict|score          # NL ask eval (needs a key)
```

## Database changes

Add a new file to `db/migrations/NNN_name.sql` (idempotent), update
`db/schema.sql` for fresh installs, and note the change. Migrations are applied
by hand in the Supabase SQL editor — call it out in your summary so it gets run.

## Git

- Branch off the default branch; keep commits small and focused.
- Author commits as the repo owner's identity (already the repo-local git config).
- End commit messages with the project's `Co-Authored-By` trailer when an AI
  assistant made the change.
