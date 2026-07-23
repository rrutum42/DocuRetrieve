# Evaluation harnesses

Measuring quality, not just asserting the code runs. Two tiers, because they
answer different questions.

## 1. Validator eval (offline, no images) — `validator_eval.py`

**Question:** when the model returns numbers that don't add up, a future date, or
a bad currency, does our validation layer catch it — without over-flagging clean
receipts?

```bash
python -m evals.validator_eval
```

Runs `app.validation.validate_receipt` over a hand-labeled set of receipts
(`dataset.py`) where each case declares which fields genuinely have a problem,
and reports precision / recall / F1 at the flagged-field level. `info`-severity
signals (e.g. line-items-don't-sum) are excluded from scoring since they're soft.

This is gated in CI by `tests/test_validator_eval.py`, so a regression fails the
build. It measures the **validator**, deterministically and for free.

## 2. Extraction-accuracy eval (needs real images) — planned

**Question:** how accurately does Gemini + our validation actually turn a *real,
messy receipt photo* into the right fields?

This needs a small corpus of **real receipt images** with **hand-labeled ground
truth** (correct merchant, date, currency, total, …). The harness will run the
full extraction pipeline over each image and report field-level accuracy, plus
`is_receipt` precision/recall on a few non-receipts.

Drop images under `evals/fixtures/images/` and labels in `evals/fixtures/labels.json`
(one object per image). Kept out of git if the receipts are personal.

> Why two tiers: the validator eval proves our *checking* logic is sound without
> spending API calls or needing private receipts; the extraction eval measures
> the *end-to-end* quality that a user actually experiences. The first guards
> every commit; the second is the headline accuracy number.

## 3. NL ask eval (synthetic, committable) — `ask_eval.py`

**Question:** does a natural-language question map to a query that returns the
right answer — including the adversarial cases (zero-expense payer, non-member,
currency filter, settle-up)?

```bash
python -m evals.ask_eval predict   # live: question -> QuerySpec (Gemini), cached
python -m evals.ask_eval score     # deterministic: run cached specs, score answers
```

Over a synthetic trip ledger (`ask_dataset.py`) with 15 labeled questions.
Because it's synthetic, the dataset and results are committed and reproducible.
The executor half is gated in CI by `tests/test_ask_eval.py`; the planner half
is the live `predict`/`score`. Latest results: 15/15 operation and answer
accuracy — see `RESULTS.md`.
