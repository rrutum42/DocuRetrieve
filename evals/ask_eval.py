"""Natural-language ask eval.

    python -m evals.ask_eval predict   # live: question -> QuerySpec (Gemini), cached
    python -m evals.ask_eval score     # deterministic: run cached specs, score answers

Measures the planner end-to-end: does a real question map to a query that yields
the right answer? Reports operation accuracy and answer accuracy, and calls out
the adversarial cases (zero-expense payer, non-member, currency filter).

The executor half is separately gated in tests/test_ask_eval.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.ask import QuerySpec, run_query
from evals.ask_dataset import BASE, CASES, MEMBER_IDS, PERSONAS, RECEIPTS, TRIP_INFO

PRED_PATH = Path(__file__).parent / "fixtures" / "ask_predictions.json"
TOL = 0.01


def _context():
    from datetime import date

    from app.ask import AskContext
    from app.schemas import Category

    return AskContext(
        today=date(2026, 7, 20),
        base_currency=BASE,
        categories=[c.value for c in Category],
        people=[p.name for p in PERSONAS],  # all names, incl. the non-member
    )


def _execute(spec: QuerySpec):
    return run_query(
        "q", spec, RECEIPTS, PERSONAS, BASE, member_ids=MEMBER_IDS, trip_info=TRIP_INFO
    )


def _answer_ok(case, resp) -> bool:
    if resp.operation != case.op:
        return False
    if case.value is not None:
        if resp.value is None or abs(resp.value - case.value) > TOL:
            return False
    if case.matched is not None and len(resp.matched) != case.matched:
        return False
    return True


def predict(force: bool = False) -> None:
    from app.ask import GeminiPlanner

    cache = {}
    if PRED_PATH.exists() and not force:
        cache = json.loads(PRED_PATH.read_text(encoding="utf-8"))
    planner = GeminiPlanner()
    ctx = _context()
    for case in CASES:
        if case.question in cache and not force:
            print(f"  cached: {case.question}")
            continue
        try:
            spec = planner.plan(case.question, ctx)
            cache[case.question] = spec.model_dump(mode="json")
            print(f"  {case.question}  ->  {spec.operation} "
                  f"{spec.paid_by or ''}{spec.category.value if spec.category else ''}"
                  f"{spec.currency or ''}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {case.question}  ->  ERROR {str(exc)[:60]}")
    PRED_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    print(f"\nWrote {len(cache)} planner outputs -> {PRED_PATH}")


def score() -> None:
    cache = json.loads(PRED_PATH.read_text(encoding="utf-8"))
    op_hits = ans_hits = 0
    rows = []
    for case in CASES:
        raw = cache.get(case.question)
        if raw is None:
            rows.append((case.question, "—", "no prediction"))
            continue
        spec = QuerySpec(**raw)
        resp = _execute(spec)
        op_ok = resp.operation == case.op
        ans_ok = _answer_ok(case, resp)
        op_hits += op_ok
        ans_hits += ans_ok
        mark = "ok " if ans_ok else "X  "
        rows.append((case.question, mark, f"op={resp.operation} val={resp.value}"))
    n = len(CASES)
    print("\nNL ask eval (planner -> executor)")
    print("=" * 74)
    for q, mark, detail in rows:
        print(f"{mark}{q[:44]:<45}{detail}")
    print("-" * 74)
    print(f"  operation accuracy: {op_hits}/{n} ({op_hits / n:.0%})")
    print(f"  answer accuracy:    {ans_hits}/{n} ({ans_hits / n:.0%})")
    print("=" * 74)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "predict"
    if cmd == "predict":
        predict(force="--force" in sys.argv)
    elif cmd == "score":
        score()
    else:
        print("usage: python -m evals.ask_eval [predict|score]")
