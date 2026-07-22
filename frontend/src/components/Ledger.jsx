// The container's ledger: a running list of confirmed receipts with a total.
// Filtering/sorting is client-side over the already-loaded rows.

import { useMemo, useState } from 'react'
import { CATEGORIES } from '../api'
import Avatar from './Avatar.jsx'
import ReceiptDetail from './ReceiptDetail.jsx'
import { money, fmtDate } from '../format'

export default function Ledger({ receipts, personas, onDelete, filterIds = null }) {
  const [category, setCategory] = useState('all')
  const [sort, setSort] = useState('date')
  const [detail, setDetail] = useState(null)

  const view = useMemo(() => {
    let rows = receipts
    if (filterIds) rows = rows.filter((r) => filterIds.has(r.id))
    if (category !== 'all') rows = rows.filter((r) => r.category === category)
    rows = [...rows].sort((a, b) => {
      if (sort === 'amount') return (b.total || 0) - (a.total || 0)
      return (b.purchase_date || '').localeCompare(a.purchase_date || '')
    })
    return rows
  }, [receipts, category, sort, filterIds])

  // Roll totals up into each receipt's base currency (usually one per container).
  // Receipts that couldn't be converted are counted separately, not hidden.
  const { totals, notConverted } = useMemo(() => {
    const acc = {}
    let nc = 0
    for (const r of view) {
      if (r.base_amount != null && r.base_currency) {
        acc[r.base_currency] = (acc[r.base_currency] || 0) + r.base_amount
      } else if (r.total != null) {
        nc += 1
      }
    }
    return { totals: acc, notConverted: nc }
  }, [view])

  if (receipts.length === 0) {
    return (
      <div className="empty">
        <div className="big">📸</div>
        No receipts here yet — upload one to get started.
      </div>
    )
  }

  return (
    <div className="ledger">
      <div className="ledger-bar">
        <div className="totals">
          {Object.entries(totals).map(([c, v]) => (
            <span key={c} className="total-pill">
              {money(v, c)}
            </span>
          ))}
          <span className="count">
            {view.length} receipt{view.length === 1 ? '' : 's'}
            {notConverted > 0 && (
              <span className="warn-count" title="Saved in original currency; not converted">
                {' '}· {notConverted} not converted
              </span>
            )}
          </span>
        </div>
        <div className="filters">
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="all">All categories</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c[0].toUpperCase() + c.slice(1)}
              </option>
            ))}
          </select>
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="date">Newest first</option>
            <option value="amount">Highest amount</option>
          </select>
        </div>
      </div>

      <ul className="receipt-list">
        {view.map((r) => {
          const payer = personas[r.paid_by_persona_id]
          return (
            <li
              key={r.id}
              className="receipt-row clickable"
              onClick={() => setDetail(r)}
              title="View receipt"
            >
              <div className="rr-main">
                <div className="rr-merchant">
                  {r.merchant || 'Unknown merchant'}
                  {r.low_confidence_fields?.length > 0 && (
                    <span className="lowconf-tag" title="Some fields were uncertain">
                      review
                    </span>
                  )}
                </div>
                <div className="rr-sub">
                  {fmtDate(r.purchase_date)}
                  {r.category && <span className="cat-chip">{r.category}</span>}
                </div>
              </div>
              <div className="rr-payer" title={payer?.name}>
                {payer && <Avatar persona={payer} size={26} />}
              </div>
              <div className="rr-total">
                {money(r.total, r.currency)}
                {r.base_amount != null &&
                  r.base_currency &&
                  r.base_currency !== r.currency && (
                    <span className="rr-converted">
                      ≈ {money(r.base_amount, r.base_currency)}
                    </span>
                  )}
              </div>
              <button
                className="rr-del"
                title="Delete receipt"
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(r)
                }}
              >
                ×
              </button>
            </li>
          )
        })}
      </ul>

      {detail && (
        <ReceiptDetail
          receipt={detail}
          personas={personas}
          onClose={() => setDetail(null)}
          onDelete={(r) => {
            setDetail(null)
            onDelete(r)
          }}
        />
      )}
    </div>
  )
}
