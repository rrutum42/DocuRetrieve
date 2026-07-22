"""Per-person / grand-total roll-up tests (pure, no HTTP)."""

from __future__ import annotations

import uuid

from app.api_models import Receipt
from app.summary import compute_summary


def rcpt(paid_by, base_amount, *, total=None):
    return Receipt(
        id=str(uuid.uuid4()),
        owner_persona_id="owner",
        paid_by_persona_id=paid_by,
        total=total if total is not None else base_amount,
        currency="USD",
        base_currency="INR",
        base_amount=base_amount,
    )


def test_grand_total_and_per_person_split():
    receipts = [
        rcpt("mom", 100.0),
        rcpt("mom", 50.0),
        rcpt("dad", 30.0),
    ]
    s = compute_summary(receipts, "INR")
    assert s.total == 180.0
    assert s.base_currency == "INR"
    assert s.receipt_count == 3
    # sorted by amount desc: mom (150) then dad (30)
    assert [(p.persona_id, p.amount, p.count) for p in s.per_person] == [
        ("mom", 150.0, 2),
        ("dad", 30.0, 1),
    ]


def test_unconverted_receipts_counted_not_summed():
    receipts = [
        rcpt("mom", 100.0),
        rcpt("mom", None, total=40.0),  # couldn't convert
    ]
    s = compute_summary(receipts, "INR")
    assert s.total == 100.0  # the unconverted 40 is excluded from the total
    assert s.not_converted == 1
    # mom still shows a count of 2 receipts, but only 100 attributed
    assert s.per_person[0].count == 2
    assert s.per_person[0].amount == 100.0


def test_empty_ledger():
    s = compute_summary([], "INR")
    assert s.total == 0.0 and s.per_person == [] and s.receipt_count == 0


def test_settle_up_balances_with_members():
    # mom paid 300, dad paid 0; members = mom, dad; fair share = 150
    receipts = [rcpt("mom", 200.0), rcpt("mom", 100.0)]
    s = compute_summary(receipts, "INR", member_ids=["mom", "dad"])
    assert s.fair_share == 150.0
    bal = {p.persona_id: p.balance for p in s.per_person}
    assert bal["mom"] == 150.0   # paid 300, share 150 -> owed 150
    assert bal["dad"] == -150.0  # paid 0, share 150 -> owes 150
    # dad appears even though he paid nothing
    assert {p.persona_id for p in s.per_person} == {"mom", "dad"}
