"""Turn the validation eval into a quality gate: if a change regresses the
validator's precision/recall on the labeled set, CI fails."""

from __future__ import annotations

from evals.validator_eval import evaluate


def test_validator_meets_quality_bar():
    res = evaluate()
    # Guard against regressions. The dataset currently scores 100%; these bars
    # leave room to grow the dataset without being brittle.
    assert res.recall >= 0.90, f"recall regressed to {res.recall:.1%}"
    assert res.precision >= 0.90, f"precision regressed to {res.precision:.1%}"


def test_no_false_positives_on_clean_receipts():
    # Over-flagging erodes trust as much as missing errors — clean receipts must
    # stay clean.
    res = evaluate()
    clean_miss = [r for r in res.rows if r[0].startswith("clean_") and r[3] != "ok"]
    assert clean_miss == [], f"clean receipts were flagged: {clean_miss}"
