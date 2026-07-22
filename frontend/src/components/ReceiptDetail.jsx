// Read-only view of an already-saved receipt: the stored original image plus the
// full structured breakdown. Opened by clicking a row in the ledger.

import Avatar from './Avatar.jsx'

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
  if (!d) return '—'
  return new Date(d + 'T00:00:00').toLocaleDateString(undefined, {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

export default function ReceiptDetail({ receipt: r, personas, onClose, onDelete }) {
  const payer = personas[r.paid_by_persona_id]
  const low = new Set(r.low_confidence_fields || [])
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s)

  const Row = ({ label, value, field }) => (
    <div className="detail-row">
      <span className="detail-label">
        {label}
        {field && low.has(field) && (
          <span className="lowconf-tag" title="Flagged uncertain at capture">
            was uncertain
          </span>
        )}
      </span>
      <span className="detail-value">{value}</span>
    </div>
  )

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal review" onClick={(e) => e.stopPropagation()}>
        <div className="review-grid">
          <div className="review-image">
            {r.image_url ? (
              <a href={r.image_url} target="_blank" rel="noreferrer" title="Open full image">
                <img src={r.image_url} alt="receipt" />
              </a>
            ) : (
              <div className="pdf-note">No image stored</div>
            )}
          </div>

          <div className="review-body">
            <h2 style={{ marginBottom: 4 }}>{r.merchant || 'Unknown merchant'}</h2>
            <div className="card-meta" style={{ marginBottom: 18 }}>
              {r.category && <span className="cat-chip">{cap(r.category)}</span>}
              <span>{fmtDate(r.purchase_date)}</span>
            </div>

            <div className="detail-list">
              <Row label="Total" value={<strong>{money(r.total, r.currency)}</strong>} field="total" />
              <Row label="Subtotal" value={money(r.subtotal, r.currency)} field="subtotal" />
              <Row label="Tax" value={money(r.tax, r.currency)} field="tax" />
              {r.tip != null && <Row label="Tip" value={money(r.tip, r.currency)} field="tip" />}
              <Row label="Currency" value={r.currency || '—'} field="currency" />
              {r.base_currency && r.base_currency !== r.currency && (
                <Row
                  label={`In ${r.base_currency}`}
                  value={
                    r.base_amount != null ? (
                      <span title={
                        r.fx_rate
                          ? `1 ${r.currency} = ${r.fx_rate} ${r.base_currency}` +
                            (r.fx_date ? ` on ${fmtDate(r.fx_date)}` : '')
                          : undefined
                      }>
                        {money(r.base_amount, r.base_currency)}
                      </span>
                    ) : (
                      <span className="muted">not converted</span>
                    )
                  }
                />
              )}
              {r.payment_method && <Row label="Payment" value={r.payment_method} />}
              <Row
                label="Paid by"
                value={
                  payer ? (
                    <span className="who">
                      <Avatar persona={payer} size={22} /> {payer.name}
                    </span>
                  ) : (
                    '—'
                  )
                }
              />
            </div>

            {r.line_items?.length > 0 && (
              <div style={{ marginTop: 18 }}>
                <div className="section-title" style={{ margin: '0 0 8px' }}>
                  Line items
                </div>
                <ul className="line-items">
                  {r.line_items.map((li, i) => (
                    <li key={i}>
                      <span>
                        {li.qty ? `${li.qty}× ` : ''}
                        {li.description}
                      </span>
                      <span>{li.amount != null ? money(li.amount, r.currency) : ''}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="modal-actions" style={{ marginTop: 22 }}>
              <button className="btn ghost" onClick={() => onDelete(r)}>
                Delete
              </button>
              <button className="btn primary" onClick={onClose}>
                Close
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
