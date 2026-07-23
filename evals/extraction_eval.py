"""Extraction-accuracy eval over REAL receipt images.

Two phases, kept separate so ground truth is established independently of the
model (otherwise we'd just be grading the model against itself):

  1. predict  — run the full pipeline (Gemini + validation) over every image in
                evals/fixtures/images/ and write predictions.json.
  2. score    — compare predictions.json against a hand-labeled labels.json and
                report field-level accuracy + is_receipt precision/recall.

    python -m evals.extraction_eval predict
    python -m evals.extraction_eval score

Images are gitignored (personal data); labels.json and results are committable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.extraction import extract_receipt

IMAGES_DIR = Path(__file__).parent / "fixtures" / "images"
PRED_PATH = Path(__file__).parent / "fixtures" / "predictions.json"
LABELS_PATH = Path(__file__).parent / "fixtures" / "labels.json"

_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}

# Objectively scorable fields. Merchant is reported alongside but NOT included in
# the accuracy number — the same store legitimately has many written forms
# ("MTNL" vs "Mahanagar Telephone Nigam Ltd"), so exact-match would mislead.
SCORED_FIELDS = ["purchase_date", "currency", "total", "category"]


def _images() -> list[Path]:
    return sorted(
        p for p in IMAGES_DIR.iterdir() if p.suffix.lower() in _MIME and p.is_file()
    )


def predict(force: bool = False) -> None:
    # Incremental by default: keep good predictions, only (re)call the API for
    # images not yet predicted or whose previous call failed. Saves scarce
    # free-tier quota when adding a few images to an existing set.
    out = {}
    if PRED_PATH.exists() and not force:
        out = json.loads(PRED_PATH.read_text(encoding="utf-8"))
    for img in _images():
        prev = out.get(img.name)
        if prev and prev.get("ok") is not False and not force:
            print(f"  {img.name}: cached, skipping")
            continue
        mime = _MIME[img.suffix.lower()]
        try:
            res = extract_receipt(img.read_bytes(), mime)
            r = res.receipt
            out[img.name] = {
                "ok": not res.used_fallback,
                "error": res.error,
                "is_receipt": r.is_receipt if r else None,
                "merchant": r.merchant if r else None,
                "purchase_date": str(r.purchase_date) if r and r.purchase_date else None,
                "currency": r.currency if r else None,
                "subtotal": r.subtotal if r else None,
                "tax": r.tax if r else None,
                "total": r.total if r else None,
                "category": r.category.value if r and r.category else None,
                "low_confidence_fields": r.low_confidence_fields if r else [],
                "validation_issues": [
                    {"field": i.field, "severity": i.severity, "message": i.message}
                    for i in (res.validation.issues if res.validation else [])
                ],
                "derived": res.validation.derived if res.validation else {},
            }
            print(f"  {img.name}: is_receipt={out[img.name]['is_receipt']} "
                  f"total={out[img.name]['total']} {out[img.name]['currency']}")
        except Exception as exc:  # noqa: BLE001
            out[img.name] = {"ok": False, "error": str(exc)}
            print(f"  {img.name}: ERROR {str(exc)[:80]}")
    PRED_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {len(out)} predictions -> {PRED_PATH}")


def _norm(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip().lower()
    return v


def _money_eq(a, b) -> bool:
    if a is None or b is None:
        return a == b
    return abs(float(a) - float(b)) <= 0.02


def _evaluable(pred: dict) -> bool:
    """A prediction we can actually score — the call succeeded."""
    return bool(pred) and pred.get("ok") is not False and pred.get("is_receipt") is not None


def score() -> None:
    preds = json.loads(PRED_PATH.read_text(encoding="utf-8"))
    labels = {k: v for k, v in json.loads(LABELS_PATH.read_text(encoding="utf-8")).items()
              if not k.startswith("_")}

    field_hits = {f: 0 for f in SCORED_FIELDS}
    field_tot = {f: 0 for f in SCORED_FIELDS}
    recv_tp = recv_fp = recv_fn = recv_tn = 0
    merchant_ok = merchant_tot = 0
    rows = []
    skipped = []

    for name, truth in labels.items():
        pred = preds.get(name, {})
        if not _evaluable(pred):
            skipped.append(name)
            continue

        t_is, p_is = truth.get("is_receipt"), pred.get("is_receipt")
        if t_is and p_is:
            recv_tp += 1
        elif not t_is and not p_is:
            recv_tn += 1
        elif not t_is and p_is:
            recv_fp += 1
        else:
            recv_fn += 1

        detail = []
        if t_is and p_is:
            for f in SCORED_FIELDS:
                tv = truth.get(f)
                if tv is None:  # illegible even to a human -> not scored
                    detail.append(f"{f}=~")
                    continue
                pv = pred.get(f)
                hit = _money_eq(tv, pv) if f == "total" else _norm(tv) == _norm(pv)
                field_tot[f] += 1
                field_hits[f] += 1 if hit else 0
                detail.append(f"{f}={'ok' if hit else 'X'}")
            # merchant, reported only
            mt = truth.get("merchant")
            if mt is not None:
                merchant_tot += 1
                mp = (pred.get("merchant") or "").lower()
                key = _norm(mt).split()[0] if _norm(mt) else ""
                merchant_ok += 1 if (key and key in mp) else 0
        rows.append((name, t_is, p_is, " ".join(detail), pred.get("merchant")))

    print("\nExtraction-accuracy eval (real receipt images)")
    print("=" * 78)
    for name, t_is, p_is, detail, merch in rows:
        flag = "" if t_is == p_is else "  <- is_receipt WRONG"
        print(f"{name.replace('WhatsApp Image ', '')[:40]:<41}{flag}")
        print(f"    {detail}   merchant~{(merch or '')[:24]}")
    print("-" * 78)
    total_hits = sum(field_hits.values())
    total_fields = sum(field_tot.values())
    for f in SCORED_FIELDS:
        if field_tot[f]:
            print(f"  {f:<15}{field_hits[f]}/{field_tot[f]} "
                  f"({field_hits[f] / field_tot[f]:.0%})")
    if total_fields:
        print(f"  {'FIELD OVERALL':<15}{total_hits}/{total_fields} "
              f"({total_hits / total_fields:.0%})")
    p = recv_tp / (recv_tp + recv_fp) if (recv_tp + recv_fp) else 1.0
    r = recv_tp / (recv_tp + recv_fn) if (recv_tp + recv_fn) else 1.0
    print(f"  {'is_receipt':<15}precision={p:.0%} recall={r:.0%} "
          f"(TP={recv_tp} FP={recv_fp} FN={recv_fn} TN={recv_tn})")
    if merchant_tot:
        print(f"  {'merchant*':<15}{merchant_ok}/{merchant_tot} "
              f"({merchant_ok / merchant_tot:.0%})  *lenient key-token match, not in overall")
    print(f"\n  evaluated {len(rows)} images; ~ = field illegible even to a human (excluded)")
    if skipped:
        print(f"  skipped {len(skipped)} (call failed / quota): "
              f"{', '.join(s.replace('WhatsApp Image ', '')[:20] for s in skipped)}")
    print("=" * 78)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "predict"
    if cmd == "predict":
        predict(force="--force" in sys.argv)
    elif cmd == "score":
        score()
    else:
        print("usage: python -m evals.extraction_eval [predict|score]")
