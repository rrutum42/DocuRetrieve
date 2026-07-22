// Per-person "who paid" split + equal-split settle-up balances for a trip.
// Computed from the loaded receipts + member list, so it updates instantly.

import { useMemo } from 'react'
import Avatar from './Avatar.jsx'
import { money } from '../format'

export default function WhoPaid({ receipts, personas, members, baseCurrency }) {
  const { total, rows, notConverted, fairShare } = useMemo(() => {
    const amt = {}
    const cnt = {}
    let sum = 0
    let nc = 0
    for (const r of receipts) {
      cnt[r.paid_by_persona_id] = (cnt[r.paid_by_persona_id] || 0) + 1
      if (r.base_amount != null) {
        sum += r.base_amount
        amt[r.paid_by_persona_id] = (amt[r.paid_by_persona_id] || 0) + r.base_amount
      } else if (r.total != null) {
        nc += 1
      }
    }
    // All members split the total equally (members who paid nothing still owe).
    const ids = members?.length
      ? members.map((m) => m.id)
      : Object.keys(cnt)
    const share = ids.length ? sum / ids.length : 0
    const people = ids
      .map((id) => ({
        id,
        amount: amt[id] || 0,
        count: cnt[id] || 0,
        balance: members?.length ? (amt[id] || 0) - share : 0,
      }))
      .sort((a, b) => b.amount - a.amount)
    return { total: sum, rows: people, notConverted: nc, fairShare: share }
  }, [receipts, members])

  if (receipts.length === 0) return null
  const settleUp = members?.length > 1 && total > 0

  return (
    <div className="whopaid">
      <div className="whopaid-total">
        <span className="wp-label">Trip total</span>
        <span className="wp-amount">{money(total, baseCurrency)}</span>
        {settleUp && (
          <span className="wp-share">{money(fairShare, baseCurrency)} each</span>
        )}
        {notConverted > 0 && <span className="wp-note">{notConverted} not converted</span>}
      </div>
      <div className="whopaid-people">
        {rows.map((p) => {
          const persona = personas[p.id]
          const owed = p.balance > 0.005
          const owes = p.balance < -0.005
          return (
            <div className="wp-chip" key={p.id} title={`${p.count} receipt${p.count === 1 ? '' : 's'}`}>
              <Avatar persona={persona} size={28} />
              <div className="wp-chip-text">
                <span className="wp-name">{persona?.name || '—'}</span>
                <span className="wp-paid">{money(p.amount, baseCurrency)} paid</span>
                {settleUp && (
                  <span className={'wp-bal ' + (owed ? 'owed' : owes ? 'owes' : 'even')}>
                    {owed
                      ? `owed ${money(p.balance, baseCurrency)}`
                      : owes
                      ? `owes ${money(-p.balance, baseCurrency)}`
                      : 'settled up'}
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
