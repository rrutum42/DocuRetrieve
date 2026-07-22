// A single container's ledger — either a trip (by :id) or your personal
// "Everyday" ledger. Upload a receipt -> always-confirm review -> it lands in
// the ledger. Per-person totals and the ask box come on Day 4.

import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import Header from '../components/Header.jsx'
import Avatar from '../components/Avatar.jsx'
import Ledger from '../components/Ledger.jsx'
import ReviewCard from '../components/ReviewCard.jsx'
import AskBox from '../components/AskBox.jsx'
import WhoPaid from '../components/WhoPaid.jsx'
import { usePersona } from '../persona.jsx'

export default function TripView({ everyday = false }) {
  const { id } = useParams()
  const { persona } = usePersona()
  const navigate = useNavigate()
  const fileInput = useRef(null)

  const [trip, setTrip] = useState(null)
  const [personas, setPersonas] = useState({})
  const [receipts, setReceipts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [adding, setAdding] = useState(false)

  const [extracting, setExtracting] = useState(false)
  const [review, setReview] = useState(null) // { result, file }
  const [askResult, setAskResult] = useState(null) // AskResponse | null

  async function load() {
    setLoading(true)
    try {
      const ps = await api.listPersonas()
      setPersonas(Object.fromEntries(ps.map((p) => [p.id, p])))
      if (everyday) {
        setReceipts(await api.listPersonalReceipts())
      } else {
        const [t, rs] = await Promise.all([
          api.getTrip(id),
          api.listTripReceipts(id),
        ])
        setTrip(t)
        setReceipts(rs)
      }
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [id, everyday])

  async function onFilePicked(e) {
    const file = e.target.files?.[0]
    e.target.value = '' // allow re-picking the same file
    if (!file) return
    setExtracting(true)
    setError(null)
    try {
      const result = await api.extract(file)
      setReview({ result, file })
    } catch (err) {
      setError(err.message)
    } finally {
      setExtracting(false)
    }
  }

  async function saveReceipt(payload, file) {
    const saved = await api.createReceipt(payload, file)
    setReceipts((rs) => [saved, ...rs])
    setReview(null)
    return saved
  }

  async function deleteReceipt(r) {
    if (!confirm(`Delete receipt from ${r.merchant || 'this merchant'}?`)) return
    await api.deleteReceipt(r.id)
    setReceipts((rs) => rs.filter((x) => x.id !== r.id))
  }

  async function deleteTrip() {
    const n = receipts.length
    const msg =
      `Delete "${trip.name}"?` +
      (n ? ` This also deletes ${n} receipt${n === 1 ? '' : 's'}.` : '') +
      ' This cannot be undone.'
    if (!confirm(msg)) return
    try {
      await api.deleteTrip(trip.id)
      navigate('/')
    } catch (e) {
      setError(e.message)
    }
  }

  if (loading) {
    return (
      <>
        <Header />
        <div className="container">Loading…</div>
      </>
    )
  }

  if (error && !review) {
    return (
      <>
        <Header />
        <div className="container">
          <Link to="/" className="back">
            ← All trips
          </Link>
          <div className="banner error">{error}</div>
        </div>
      </>
    )
  }

  const title = everyday ? 'My Everyday' : trip.name
  const members = everyday
    ? [persona]
    : trip.member_ids.map((mid) => personas[mid]).filter(Boolean)

  return (
    <>
      <Header />
      <div className="container">
        <Link to="/" className="back">
          ← All trips
        </Link>
        <div className="trip-head">
          <div>
            <h1 style={{ margin: '4px 0 6px', letterSpacing: '-0.02em' }}>{title}</h1>
            <div className="card-meta">
              {everyday ? (
                <span>Private to {persona.name}</span>
              ) : (
                <>
                  <span className="avatar-stack">
                    {members.map((m) => (
                      <Avatar key={m.id} persona={m} size={26} />
                    ))}
                  </span>
                  <span>{members.map((m) => m.name).join(', ')}</span>
                  {trip.base_currency && (
                    <span className="base-cur-pill" title="Trip totals roll up into this currency">
                      Totals in {trip.base_currency}
                    </span>
                  )}
                  <button className="btn ghost" onClick={() => setAdding(true)}>
                    + Add people
                  </button>
                </>
              )}
            </div>
          </div>
          <div>
            <input
              ref={fileInput}
              type="file"
              accept="image/*,application/pdf"
              style={{ display: 'none' }}
              onChange={onFilePicked}
            />
            <button
              className="btn primary"
              onClick={() => fileInput.current?.click()}
              disabled={extracting}
            >
              {extracting ? 'Reading receipt…' : '＋ Add receipt'}
            </button>
            {!everyday && trip.created_by === persona.id && (
              <button className="btn danger-link" onClick={deleteTrip}>
                Delete trip
              </button>
            )}
          </div>
        </div>

        {error && <div className="banner error">{error}</div>}

        {receipts.length > 0 && (
          <AskBox
            ask={everyday ? api.askPersonal : (q) => api.askTrip(trip.id, q)}
            onResult={setAskResult}
            examples={
              everyday
                ? ['How much in total?', 'What did I spend on groceries?', 'How many receipts?']
                : [
                    'How much in total?',
                    'What did we spend on dining?',
                    `How much is owed to ${persona.name}?`,
                  ]
            }
          />
        )}

        {!everyday && (
          <WhoPaid
            receipts={receipts}
            personas={personas}
            members={members}
            baseCurrency={trip.base_currency}
          />
        )}

        <Ledger
          receipts={receipts}
          personas={personas}
          onDelete={deleteReceipt}
          filterIds={askResult ? new Set(askResult.matched.map((m) => m.id)) : null}
        />
      </div>

      {review && (
        <ReviewCard
          result={review.result}
          file={review.file}
          members={members}
          currentPersona={persona}
          tripId={everyday ? null : trip.id}
          onClose={() => setReview(null)}
          onSaved={saveReceipt}
        />
      )}

      {adding && !everyday && (
        <AddPeopleModal
          trip={trip}
          personas={personas}
          onClose={() => setAdding(false)}
          onUpdated={(t) => {
            setTrip(t)
            setAdding(false)
          }}
        />
      )}
    </>
  )
}

function AddPeopleModal({ trip, personas, onClose, onUpdated }) {
  const candidates = Object.values(personas).filter(
    (p) => !trip.member_ids.includes(p.id),
  )
  const [selected, setSelected] = useState(new Set())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  function toggle(id) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  async function submit(e) {
    e.preventDefault()
    if (selected.size === 0) return
    setSaving(true)
    try {
      const updated = await api.addMembers(trip.id, [...selected])
      onUpdated(updated)
    } catch (e) {
      setError(e.message)
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2>Add people to {trip.name}</h2>
        {error && <div className="banner error">{error}</div>}
        {candidates.length === 0 ? (
          <p style={{ color: 'var(--ink-soft)' }}>
            Everyone's already on this trip. Create more profiles to share it wider.
          </p>
        ) : (
          <div className="chips" style={{ marginBottom: 20 }}>
            {candidates.map((p) => (
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
        )}
        <div className="modal-actions">
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            className="btn primary"
            disabled={saving || selected.size === 0}
          >
            {saving ? 'Adding…' : 'Add'}
          </button>
        </div>
      </form>
    </div>
  )
}
