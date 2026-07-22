// Netflix-style entry screen: pick who you are, or create a new profile.

import { useEffect, useState } from 'react'
import { api } from '../api'
import { usePersona } from '../persona.jsx'
import Avatar, { AVATAR_PALETTE } from '../components/Avatar.jsx'

export default function PersonaPicker() {
  const { choose } = usePersona()
  const [people, setPeople] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [creating, setCreating] = useState(false)

  async function load() {
    setLoading(true)
    try {
      setPeople(await api.listPersonas())
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="picker">
      <h1>
        Docu<span style={{ color: 'var(--accent)' }}>Retrieve</span>
      </h1>
      <p>Who's using the ledger?</p>

      {error && (
        <div className="banner error" style={{ maxWidth: 460 }}>
          Couldn't load profiles: {error}
        </div>
      )}

      <div className="picker-grid">
        {people.map((p) => (
          <button key={p.id} className="picker-item" onClick={() => choose(p)}>
            <Avatar persona={p} size={92} />
            <span className="name">{p.name}</span>
          </button>
        ))}

        <button className="picker-item add" onClick={() => setCreating(true)}>
          <span className="avatar" style={{ width: 92, height: 92 }}>
            +
          </span>
          <span className="name">New profile</span>
        </button>
      </div>

      {loading && <p style={{ marginTop: 24 }}>Loading profiles…</p>}

      {creating && (
        <NewProfileModal
          onClose={() => setCreating(false)}
          onCreated={(p) => {
            setCreating(false)
            choose(p) // jump straight in as the new profile
          }}
        />
      )}
    </div>
  )
}

function NewProfileModal({ onClose, onCreated }) {
  const [name, setName] = useState('')
  const [color, setColor] = useState(AVATAR_PALETTE[0])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    try {
      const p = await api.createPersona(name.trim(), color)
      onCreated(p)
    } catch (e) {
      setError(e.message)
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2>New profile</h2>
        {error && <div className="banner error">{error}</div>}
        <div className="field">
          <label>Name</label>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Mom"
            maxLength={60}
          />
        </div>
        <div className="field">
          <label>Color</label>
          <div className="swatches">
            {AVATAR_PALETTE.map((c) => (
              <button
                type="button"
                key={c}
                className={'swatch' + (c === color ? ' selected' : '')}
                style={{ background: c }}
                onClick={() => setColor(c)}
                aria-label={'color ' + c}
              />
            ))}
          </div>
        </div>
        <div className="modal-actions">
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn primary" disabled={saving || !name.trim()}>
            {saving ? 'Creating…' : 'Create'}
          </button>
        </div>
      </form>
    </div>
  )
}
