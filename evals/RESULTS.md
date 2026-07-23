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
