// Create a trip: name, optional dates, and share it with other profiles
// (Splitwise-style). The creator is always a member server-side.

import { useEffect, useState } from 'react'
import { api, CURRENCIES } from '../api'
import { usePersona } from '../persona.jsx'
import Avatar from './Avatar.jsx'

export default function CreateTripModal({ onClose, onCreated }) {
  const { persona } = usePersona()
  const [name, setName] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [currency, setCurrency] = useState('INR')
  const [people, setPeople] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .listPersonas()
      .then((all) => setPeople(all.filter((p) => p.id !== persona.id)))
      .catch(() => {})
  }, [persona.id])

  function toggle(id) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  async function submit(e) {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    try {
      const trip = await api.createTrip({
        name: name.trim(),
        start_date: start || null,
        end_date: end || null,
        base_currency: currency,
        member_ids: [...selected],
      })
      onCreated(trip)
    } catch (e) {
      setError(e.message)
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2>New trip</h2>
        {error && <div className="banner error">{error}</div>}

        <div className="field">
          <label>Trip name</label>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. France 2026"
            maxLength={120}
          />
        </div>

        <div className="row">
          <div className="field">
            <label>Start date</label>
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </div>
          <div className="field">
            <label>End date</label>
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </div>
        </div>

        <div className="field">
          <label>Base currency</label>
          <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {CURRENCIES.map(([code, label]) => (
              <option key={code} value={code}>
                {label} ({code})
              </option>
            ))}
          </select>
          <div className="field-hint">
            All this trip's totals roll up into this currency, converted at each
            receipt's date.
          </div>
        </div>

        {people.length > 0 && (
          <div className="field">
            <label>Share with</label>
            <div className="chips">
              {people.map((p) => (
                <button
                  type="button"
                  key={p.id}
                  className={'chip' + (selected.has(p.id) ? ' selected' : '')}
                  onClick={() => toggle(p.id)}
                >
                  <Avatar persona={p} size={22} />
                  {p.name}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn primary" disabled={saving || !name.trim()}>
            {saving ? 'Creating…' : 'Create trip'}
          </button>
        </div>
      </form>
    </div>
  )
}
