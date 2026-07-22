"""Per-container roll-ups: the grand total, the per-person 'who paid' split, and
(for trips) equal-split settle-up balances.

Pure functions over already-loaded receipts, so they're trivially testable. All
money is in the container's base currency; receipts that couldn't be converted
are counted, not silently dropped.

Settle-up model: an **equal split** of the converted total across all trip
members. A member's balance = what they paid − their fair share; positive means
they're owed money, negative means they owe. (Per-expense participant splits are
out of scope — we don't track who shared each receipt.)
"""

from __future__ import annotations

from .api_models import LedgerSummary, PersonPaid, Receipt


def compute_summary(
    receipts: list[Receipt],
    base_currency: str,
    member_ids: list[str] | None = None,
) -> LedgerSummary:
    total = 0.0
    not_converted = 0
    paid_amount: dict[str, float] = {}
    paid_count: dict[str, int] = {}

    for r in receipts:
        paid_count[r.paid_by_persona_id] = paid_count.get(r.paid_by_persona_id, 0) + 1
        if r.base_amount is not None:
            total += r.base_amount
            paid_amount[r.paid_by_persona_id] = (
                paid_amount.get(r.paid_by_persona_id, 0.0) + r.base_amount
            )
        elif r.total is not None:
            not_converted += 1

    # Which personas to report on: all trip members (so someone who paid nothing
    # still shows a balance), or just the payers for the personal ledger.
    people = list(member_ids) if member_ids else list(paid_count.keys())
    for pid in paid_count:  # include any payer not in member_ids (defensive)
        if pid not in people:
            people.append(pid)

    fair_share = round(total / len(member_ids), 2) if member_ids else 0.0

    per_person = [
        PersonPaid(
            persona_id=pid,
            amount=round(paid_amount.get(pid, 0.0), 2),
            count=paid_count.get(pid, 0),
            balance=round(paid_amount.get(pid, 0.0) - fair_share, 2)
            if member_ids
            else 0.0,
        )
        for pid in people
    ]
    per_person.sort(key=lambda p: p.amount, reverse=True)

    return LedgerSummary(
        base_currency=base_currency,
        total=round(total, 2),
        receipt_count=len(receipts),
        not_converted=not_converted,
        fair_share=fair_share,
        per_person=per_person,
    )
