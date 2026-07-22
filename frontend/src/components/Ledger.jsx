// The container's ledger: a running list of confirmed receipts with a total.
// Filtering/sorting is client-side over the already-loaded rows.

import { useMemo, useState } from 'react'
import { CATEGORIES } from '../api'
import Avatar from './Avatar.jsx'
import ReceiptDetail from './ReceiptDetail.jsx'

function money(amount, currency) {
  if (amount == null) return '—'
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency || 'USD',
    }).format(amount)
  } catch {
    return `${amount} ${currency || ''}`.trim()
  }
}

function fmtDate(d) {
  if (!d) return ''
  return new Date(d + 'T00:00:00').toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export default function Ledger({ receipts, personas, onDelete }) {
  const [category, setCategory] = useState('all')
  const [sort, setSort] = useState('date')
  const [detail, setDetail] = useState(null)

  const view = useMemo(() => {
    let rows = receipts
    if (category !== 'all') rows = rows.filter((r) => r.category === category)
    rows = [...rows].sort((a, b) => {
      if (sort === 'amount') return (b.total || 0) - (a.total || 0)
      return (b.purchase_date || '').localeCompare(a.purchase_date || '')
    })
    return rows
  }, [receipts, category, sort])

  // Totals per currency (a trip may mix currencies).
  const totals = useMemo(() => {
    const acc = {}
    for (const r of view) {
      if (r.total == null) continue
      const c = r.currency || 'USD'
      acc[c] = (acc[c] || 0) + r.total
    }
    return acc
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
              <div className="rr-total">{money(r.total, r.currency)}</div>
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
