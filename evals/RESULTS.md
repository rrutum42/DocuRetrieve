# Extraction eval results

Run: `python -m evals.extraction_eval predict` then `score`.
Model: `gemini-flash-latest` (vision) + the validation layer.

## The test set (16 images: 12 real receipts + 4 non-receipts)

Ground truth was read **independently** from each image, then compared to the
model's output. The set was chosen to be hard, not flattering:

| # | Image | What makes it hard |
|---|-------|--------------------|
| 1 | Frankfurt airport duty-free | foreign currency (EUR), crumpled thermal |
| 2 | Petus, Mumbai | normal baseline |
| 3 | Thakur College fee receipt | **fully handwritten** amounts |
| 4 | Mahalaxmi, Goa | **blurry, low light** |
| 5 | Hospital med list | **handwritten**, ambiguous total |
| 6 | BMC municipal fine | **Marathi/Devanagari + handwritten** |
| 7 | Samarth water-purifier AMC | handwritten |
| 8 | The Bombay Canteen | long bill, angled, small text |
| 9 | Markaiz, Lonavala | very long itemized bill |
| 10 | Gangar Eyenation | **image rotated 90°** |
| 11 | Adani Electricity | utility bill layout |
| 12 | MTNL | telecom bill, acronym merchant |
| 13 | Aquarium photo | non-receipt (should reject) |
| 14 | Blank hospital form + math notes | **adversarial** non-receipt (hospital letterhead, no transaction) |
| 15 | Lenovo laptop box label | **adversarial** non-receipt (barcodes, model, date — looks purchase-y) |
| 16 | Excalidraw diagram on a screen | non-receipt (should reject) |

## Results (all 16 evaluated)

| Field | Accuracy |
|-------|----------|
| purchase_date | 11/11 (100%) |
| currency | 12/12 (100%) |
| total | 11/11 (100%) |
| category | 12/12 (100%) |
| **objective fields overall** | **46/46 (100%)** |
| **is_receipt** | **precision 100%, recall 100%** (TP=12, TN=4, FP=0, FN=0) |
| merchant* | 10/11 (91%) |

The `is_receipt` result is the notable one: **4/4 non-receipts correctly
rejected, including both adversarial cases** — the model was not fooled by a
hospital letterhead on a page of math notes, nor by a product barcode label that
superficially resembles a purchase.

\* merchant is a lenient key-token match and **excluded from the headline
number** — the same store has many valid written forms ("MTNL" vs "Mahanagar
Telephone Nigam Ltd", the one miss). Reported for transparency only.

## Honesty notes (what the number does and doesn't claim)

- **Small set (16).** This is a spot-check on hard cases, not a large benchmark.
  It says "the pipeline handles genuinely messy real-world receipts and rejects
  non-receipts," not "it is 100% accurate in general."
- **2 fields excluded as illegible** — the hospital total (`1,443 +1,200`, truly
  ambiguous) and the BMC year — were left `null` in the labels rather than
  guessed, so we don't credit or penalize the model on what a human can't read.
- **Quota note** — one earlier run hit the free-tier daily cap (429) on a single
  image; the graceful-fallback path handled it without crashing, and it
  extracted correctly on the next day's quota. `predict` is incremental, so
  adding images only spends calls on the new ones.

The takeaway: across handwritten, blurry, non-Latin-script, rotated, and
foreign-currency receipts, the model + validation layer read every objectively
legible field correctly — and correctly rejected every non-receipt, including
adversarial ones.

---

# NL ask eval results

Run: `python -m evals.ask_eval predict` then `score`.
Model: `gemini-flash-lite-latest` (the planner) + the deterministic executor.

**Question:** does a real natural-language question map to a query that returns
the *right* answer — especially on the cases that used to be bugs?

The dataset (`evals/ask_dataset.py`) is a synthetic trip ledger (Mom/Dad/Kid,
5 receipts, one in USD) with 15 labeled questions. Because it's synthetic, the
dataset, the planner outputs, and these results are all committed and
reproducible.

## Results

| Metric | Result |
|--------|--------|
| operation accuracy | 15/15 (100%) |
| **answer accuracy** | **15/15 (100%)** |

Every question mapped to the right operation *and* produced the correct number —
including the adversarial cases that motivated earlier fixes:

- **"How much did Kid pay?"** (a member who paid for nothing) → **0**, not "no
  receipts found".
- **"How much did Stranger pay?"** (someone not on the trip) → **0**, not the
  whole-trip total (the bug we fixed by giving the planner all persona names).
- **"How many expenses were in USD?"** → native-currency filter, count = 1.
- **"How much is owed to Mom?" / "How much does Kid owe?"** → settle-up balances
  with the correct sign.
- **"Who is on this trip?" / "Give me an overview"** → metadata operations.

## Two tiers (same split as the extraction eval)

- **Executor** (`run_query`) is gated in CI by `tests/test_ask_eval.py` — every
  case's *correct* QuerySpec must produce the labeled answer, deterministically,
  with no API calls. This guards the query engine against regressions.
- **Planner** (Gemini) is the live half above — it measures the LLM step that
  turns a question into that QuerySpec.

## Honesty notes

- **Small, synthetic set (15).** It proves the planner handles the intended
  question shapes and the known failure modes, not that it's correct on every
  possible phrasing. Real-world paraphrase robustness would need a larger set.
- The executor is fully deterministic and CI-gated; only the planner step
  depends on the model.

## Update: `breakdown` operation (per-person / by-category splits)

The query language gained a `breakdown` operation with a `group_by` dimension
(`category | paid_by | currency | merchant`), so questions like "how much did
each person spend?" and "what did we spend by category?" now have a valid target
instead of collapsing to a single number.

- **Executor gate:** the dataset grew to 18 cases (3 breakdown cases added) and
  `tests/test_ask.py` covers grouping by category, by person, filter composition
  ("break down dining by person"), the default-to-category path, and the empty
  case. All deterministic and green in CI.
- **Not yet re-scored live:** the answer/operation accuracy numbers above were
  measured on the earlier 15 cases. The live planner mapping for the new
  breakdown question shapes still needs a keyed `python -m evals.ask_eval`
  run — those numbers are **not** claimed here yet. The planner prompt gained
  few-shot examples to steer the weak `flash-lite` model toward the right
  operation, but that's an intervention to *verify*, not a measured result.

## Update: `compare`, top-N/sorted `list`, `share`, and `unsupported`

Running the **live** planner over ~25 realistic paraphrases (not just the dataset
phrasings) surfaced that operation classification was already solid — the wrong
answers all came from the **query language being too narrow** to express the
question. Four bounded additions close those gaps, all inside the same
validated-spec / deterministic-executor design:

| Question shape that used to fail | Now maps to |
|---|---|
| "did we spend more on dining **or** fuel?", "who spent more, Mom or Dad?", "how much **more** did Mom pay than Dad?" | `compare` (`group_by` + `compare_subjects`) → leader + the exact gap; equal totals answer "it's a tie" |
| "what are our **3 biggest** expenses?" (was `max` → 1 row) | `list` with `sort=amount_desc, limit=3`, itemised |
| "receipts **most to least** expensive" | `list` with `sort` (ordered, with amounts) |
| "what **percent** did Dad cover?", "what fraction was food?" | `breakdown` — each `BreakdownRow` now carries a `share` (% of total) |
| "what's the **weather**?", off-ledger chit-chat | `unsupported` — an honest refusal, never a fabricated number |

- **Executor gate:** grew to **25 cases** and is green in CI
  (`tests/test_ask.py` + the parametrized `tests/test_ask_eval.py`), including the
  dining-vs-fuel **tie**, a compare subject with **zero** receipts (a real 0, not
  a miss), top-N ordering, and the unsupported refusal. Fully deterministic.
- **Planner model unchanged** (`flash-lite`): the diagnostic showed the model
  wasn't the bottleneck, so the separate lighter quota bucket still stands. The
  prompt gained the new operations, the `sort`/`limit`/`compare_subjects` fields,
  and a worked example per shape.

### Live re-score (measured, all 25 cases)

| Metric | Result |
|--------|--------|
| operation accuracy | **25/25 (100%)** |
| answer accuracy | **25/25 (100%)** |

Every one of the new shapes mapped correctly and produced the right answer live:
`compare` (Mom-vs-Dad → gap 100; dining-vs-fuel → tie), top-N `list`
(3 biggest, sorted), the `share`/percentage breakdown, and the `unsupported`
refusal ("what's the weather in Goa?").

- **One real miss, found and fixed:** the first live run scored 24/25 — "what
  percent did Mom pay?" chose `breakdown` (right) but *also* set `paid_by=Mom`,
  which filtered the split to Mom alone and collapsed the denominator (₹450, her
  own total, not her share of ₹800). Added a planner rule that percentage
  questions must not filter to the subject; the re-run is 25/25. This is logged
  honestly because it's exactly the kind of failure the eval exists to catch.
- **Reproducibility:** planner outputs are cached in
  `evals/fixtures/ask_predictions.json` and the dataset is synthetic, so this
  number is committed and re-scorable offline with `python -m evals.ask_eval
  score`.
