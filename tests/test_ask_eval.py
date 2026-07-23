"""Executor gate: for every dataset case, the CORRECT QuerySpec must produce the
labeled answer. Deterministic (no Gemini), so it runs in CI and guards the query
engine against regressions across the full question set — including the
adversarial cases (zero-expense payer, non-member, currency, settle-up)."""

from __future__ import annotations

import pytest

from evals.ask_dataset import BASE, CASES, MEMBER_IDS, PERSONAS, RECEIPTS, TRIP_INFO
from app.ask import run_query


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.question)
def test_executor_produces_labeled_answer(case):
    resp = run_query(
        case.question,
        case.hand_spec,
        RECEIPTS,
        PERSONAS,
        BASE,
        member_ids=MEMBER_IDS,
        trip_info=TRIP_INFO,
    )
    assert resp.operation == case.op
    if case.value is not None:
        assert resp.value is not None, f"{case.question}: expected {case.value}, got None"
        assert abs(resp.value - case.value) < 0.01, (
            f"{case.question}: expected {case.value}, got {resp.value}"
        )
    if case.matched is not None:
        assert len(resp.matched) == case.matched
