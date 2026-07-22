// A single container's ledger — either a trip (by :id) or your personal
// "Everyday" ledger. Day 2 shows the header, members, and add-member flow;
// the receipt list, upload, per-person totals, and ask box arrive on Day 3.

import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import Header from '../components/Header.jsx'
import Avatar from '../components/Avatar.jsx'
import { usePersona } from '../persona.jsx'

export default function TripView({ everyday = false }) {
  const { id } = useParams()
  const { persona } = usePersona()
  const [trip, setTrip] = useState(null)
  const [personas, setPersonas] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [adding, setAdding] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const ps = await api.listPersonas()
      setPersonas(Object.fromEntries(ps.map((p) => [p.id, p])))
      if (!everyday) setTrip(await api.getTrip(id))
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

  if (loading) {
    return (
      <>
        <Header />
        <div className="container">Loading…</div>
      </>
    )
  }

  if (error) {
    return (
      <>
        <Header />
        <div className="container">
          <div className="banner error">{error}</div>
        </div>
      </>
    )
  }

  const title = everyday ? 'My Everyday' : trip.name
  const members = everyday ? [] : trip.member_ids.map((mid) => personas[mid]).filter(Boolean)

  return (
    <>
      <Header />
      <div className="container">
        <h1 style={{ margin: '4px 0 6px', letterSpacing: '-0.02em' }}>{title}</h1>
        <div className="card-meta" style={{ marginBottom: 24 }}>
          {everyday ? (
            <span>Private to {persona.name}</span>
          ) : (
            <>
              <span className="avatar-stack">
                {members.map((m) => (
                  <Avatar key={m.id} persona={m} size={26} />
                ))}
              </span>
              <span>
                {members.map((m) => m.name).join(', ')}
              </span>
              <button className="btn ghost" onClick={() => setAdding(true)}>
                + Add people
              </button>
            </>
          )}
        </div>

        <div className="banner">
          🚧 Receipt upload, the always-confirm review, per-person totals, and the
          ask box land next (Day 3). This container is ready to receive them.
        </div>

        <div className="empty">
          <div className="big">📸</div>
          No receipts here yet.
        </div>
      </div>

      {adding && (
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
