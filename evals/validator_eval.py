"""Run the validation layer over the labeled dataset and report how well it
catches the injected problems: precision, recall, F1 at the flagged-field level.

    python -m evals.validator_eval

The same evaluate() is asserted against a quality bar in
tests/test_validator_eval.py, so regressions fail CI.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.validation import validate_receipt
from evals.dataset import CASES, FIXED_TODAY, Case

# Fields flagged at these severities count as a "catch". 'info' is a soft signal
# (e.g. line-items-don't-sum) and is intentionally excluded from scoring.
SCORING_SEVERITIES = {"warning", "error"}


@dataclass
class EvalResult:
    tp: int
    fp: int
    fn: int
    rows: list[tuple]

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 1.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def case_accuracy(self) -> float:
        exact = sum(1 for row in self.rows if row[3] == "ok")
        return exact / len(self.rows) if self.rows else 1.0


def evaluate(cases: list[Case] = CASES) -> EvalResult:
    tp = fp = fn = 0
    rows = []
    for c in cases:
        report = validate_receipt(c.receipt, today=FIXED_TODAY)
        actual = {i.field for i in report.issues if i.severity in SCORING_SEVERITIES}
        expected = c.expected_flags
        ctp, cfp, cfn = (
            len(actual & expected),
            len(actual - expected),
            len(expected - actual),
        )
        tp, fp, fn = tp + ctp, fp + cfp, fn + cfn
        verdict = "ok" if (cfp == 0 and cfn == 0) else "MISS"
        rows.append((c.name, sorted(expected), sorted(actual), verdict))
    return EvalResult(tp=tp, fp=fp, fn=fn, rows=rows)


def main() -> None:
    res = evaluate()
    print("\nValidation-layer eval")
    print("=" * 68)
    print(f"{'case':<32}{'expected':<14}{'flagged':<14}{'':<4}")
    print("-" * 68)
    for name, expected, actual, verdict in res.rows:
        mark = "  " if verdict == "ok" else "X "
        exp = ",".join(expected) or "-"
        act = ",".join(actual) or "-"
        print(f"{mark}{name:<30}{exp:<14}{act:<14}")
    print("-" * 68)
    print(
        f"cases: {len(res.rows)}  |  exact-case accuracy: {res.case_accuracy:.0%}\n"
        f"field-level  TP={res.tp} FP={res.fp} FN={res.fn}\n"
        f"precision={res.precision:.1%}  recall={res.recall:.1%}  F1={res.f1:.1%}"
    )
    print("=" * 68)


if __name__ == "__main__":
    main()
