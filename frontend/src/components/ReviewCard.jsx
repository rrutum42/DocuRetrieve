// The always-confirm review step. The model proposes; the human confirms.
// Original image on the left, editable extracted fields on the right, with
// low-confidence fields visibly flagged. Non-receipts and unreadable uploads
// are handled explicitly instead of saving garbage.

import { useMemo, useState } from 'react'
import { CATEGORIES } from '../api'

function num(v) {
  if (v === '' || v == null) return null
  const n = parseFloat(v)
  return Number.isNaN(n) ? null : n
}

export default function ReviewCard({
  result, // full ExtractionResult { receipt, raw, used_fallback, error }
  file,
  members, // personas allowed as paid_by
  currentPersona,
  tripId,
  onClose,
  onSaved,
}) {
  const preview = useMemo(() => URL.createObjectURL(file), [file])
  const extraction = result?.receipt
  const isRejected = extraction && extraction.is_receipt === false
  const isUnreadable = !extraction || result?.used_fallback

  const low = new Set(extraction?.low_confidence_fields || [])
  const issues = result?.validation?.issues || []
  const derivedKeys = Object.keys(result?.validation?.derived || {})

  const [form, setForm] = useState(() => ({
    merchant: extraction?.merchant ?? '',
    purchase_date: extraction?.purchase_date ?? '',
    currency: extraction?.currency ?? '',
    subtotal: extraction?.subtotal ?? '',
    tax: extraction?.tax ?? '',
    tip: extraction?.tip ?? '',
    total: extraction?.total ?? '',
    category: extraction?.category ?? 'other',
    payment_method: extraction?.payment_method ?? '',
    paid_by: currentPersona.id,
  }))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  function set(k, v) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  // A receipt must have a positive total to be saveable — this blocks zero-cost
  // rows and non-receipts (which have no real total).
  const totalNum = num(form.total)
  const canSave = totalNum !== null && totalNum > 0

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const payload = {
        trip_id: tripId,
        paid_by_persona_id: form.paid_by,
        merchant: form.merchant || null,
        purchase_date: form.purchase_date || null,
        currency: form.currency || null,
        subtotal: num(form.subtotal),
        tax: num(form.tax),
        tip: num(form.tip),
        total: num(form.total),
        category: form.category || null,
        payment_method: form.payment_method || null,
        line_items: extraction?.line_items || [],
        low_confidence_fields: extraction?.low_confidence_fields || [],
        raw_extraction: extraction || null,
      }
      const saved = await onSaved(payload, file)
      return saved
    } catch (e) {
      setError(e.message)
      setSaving(false)
    }
  }

  const lowHint = (field) =>
    low.has(field) ? (
      <span className="lowconf-tag" title="The reader wasn't sure — please check">
        check
      </span>
    ) : null

  const cls = (field) => 'field' + (low.has(field) ? ' lowconf' : '')

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal review"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="review-grid">
          <div className="review-image">
            {file.type === 'application/pdf' ? (
              <div className="pdf-note">📄 PDF uploaded</div>
            ) : (
              <img src={preview} alt="receipt" />
            )}
          </div>

          <div className="review-body">
            {isRejected ? (
              <div className="reject">
                <div className="big">🤔</div>
                <h2>This doesn't look like a receipt</h2>
                <p>{extraction.rejection_reason || 'No receipt detected in the image.'}</p>
                <div className="modal-actions">
                  <button className="btn primary" onClick={onClose}>
                    Try another
                  </button>
                </div>
              </div>
            ) : (
              <>
                <h2>Review &amp; confirm</h2>
                {isUnreadable && (
                  <div className="banner">
                    {result?.error === 'rate_limited'
                      ? '⏳ The daily free limit for auto-reading receipts has been reached (the AI reader runs on a free tier — about 20 per day). You can still enter the details manually below, or try again tomorrow.'
                      : "We couldn't read this automatically. Fill in what you can — nothing is saved until you confirm."}
                  </div>
                )}
                {!isUnreadable && issues.length > 0 && (
                  <div className="validation-panel">
                    {issues.map((iss, i) => (
                      <div key={i} className={'v-issue ' + iss.severity}>
                        <span className="v-ic">
                          {iss.severity === 'error'
                            ? '⛔'
                            : iss.severity === 'warning'
                            ? '⚠'
                            : 'ℹ'}
                        </span>
                        <span>{iss.message}</span>
                      </div>
                    ))}
                  </div>
                )}
                {!isUnreadable && derivedKeys.length > 0 && (
                  <div className="banner subtle">
                    We filled in {derivedKeys.join(', ')} from the other amounts —
                    please confirm {derivedKeys.length === 1 ? 'it' : 'them'}.
                  </div>
                )}
                {!isUnreadable && issues.length === 0 && low.size > 0 && (
                  <div className="banner">
                    A few fields were hard to read (flagged below). Give them a
                    quick check.
                  </div>
                )}
                {error && <div className="banner error">{error}</div>}

                <div className={cls('merchant')}>
                  <label>Merchant {lowHint('merchant')}</label>
                  <input
                    value={form.merchant}
                    onChange={(e) => set('merchant', e.target.value)}
                    placeholder="e.g. Boulangerie Paul"
                  />
                </div>

                <div className="row">
                  <div className={cls('purchase_date')}>
                    <label>Date {lowHint('purchase_date')}</label>
                    <input
                      type="date"
                      value={form.purchase_date || ''}
                      onChange={(e) => set('purchase_date', e.target.value)}
                    />
                  </div>
                  <div className={cls('currency')} style={{ maxWidth: 110 }}>
                    <label>Currency {lowHint('currency')}</label>
                    <input
                      value={form.currency}
                      onChange={(e) => set('currency', e.target.value.toUpperCase())}
                      placeholder="EUR"
                      maxLength={3}
                    />
                  </div>
                </div>

                <div className="row">
                  <div className={cls('subtotal')}>
                    <label>Subtotal {lowHint('subtotal')}</label>
                    <input value={form.subtotal ?? ''} onChange={(e) => set('subtotal', e.target.value)} inputMode="decimal" />
                  </div>
                  <div className={cls('tax')}>
                    <label>Tax {lowHint('tax')}</label>
                    <input value={form.tax ?? ''} onChange={(e) => set('tax', e.target.value)} inputMode="decimal" />
                  </div>
                  <div className={cls('tip')}>
                    <label>Tip {lowHint('tip')}</label>
                    <input value={form.tip ?? ''} onChange={(e) => set('tip', e.target.value)} inputMode="decimal" />
                  </div>
                </div>

                <div className={cls('total')}>
                  <label>Total {lowHint('total')}</label>
                  <input
                    className="total-input"
                    value={form.total ?? ''}
                    onChange={(e) => set('total', e.target.value)}
                    inputMode="decimal"
                    placeholder="0.00"
                  />
                </div>

                <div className="row">
                  <div className={cls('category')}>
                    <label>Category</label>
                    <select value={form.category} onChange={(e) => set('category', e.target.value)}>
                      {CATEGORIES.map((c) => (
                        <option key={c} value={c}>
                          {c[0].toUpperCase() + c.slice(1)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label>Paid by</label>
                    <select value={form.paid_by} onChange={(e) => set('paid_by', e.target.value)}>
                      {members.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {extraction?.line_items?.length > 0 && (
                  <div className="field">
                    <label>Line items ({extraction.line_items.length})</label>
                    <ul className="line-items">
                      {extraction.line_items.map((li, i) => (
                        <li key={i}>
                          <span>{li.description}</span>
                          <span>{li.amount != null ? li.amount : ''}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {!canSave && (
                  <div className="save-hint">
                    {totalNum !== null && totalNum <= 0
                      ? 'Total must be greater than 0.'
                      : 'Enter a total to save — if this isn’t a receipt, discard it.'}
                  </div>
                )}
                <div className="modal-actions">
                  <button className="btn ghost" onClick={onClose} disabled={saving}>
                    {canSave ? 'Cancel' : 'Discard'}
                  </button>
                  <button
                    className="btn primary"
                    onClick={save}
                    disabled={saving || !canSave}
                  >
                    {saving ? 'Saving…' : 'Confirm & save'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
