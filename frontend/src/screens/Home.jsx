// Home: your personal "Everyday" ledger + a grid of trips (albums) you created
// or were shared into, plus a tile to start a new trip.

import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import Header from '../components/Header.jsx'
import Avatar from '../components/Avatar.jsx'
import CreateTripModal from '../components/CreateTripModal.jsx'
import TripCover from '../components/TripCover.jsx'

function dateRange(t) {
  if (!t.start_date && !t.end_date) return null
  const fmt = (d) =>
    new Date(d + 'T00:00:00').toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
    })
  if (t.start_date && t.end_date) return `${fmt(t.start_date)} – ${fmt(t.end_date)}`
  return fmt(t.start_date || t.end_date)
}

export default function Home() {
  const navigate = useNavigate()
  const [trips, setTrips] = useState([])
  const [personas, setPersonas] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [creating, setCreating] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const [ts, ps] = await Promise.all([api.listTrips(), api.listPersonas()])
      setTrips(ts)
      setPersonas(Object.fromEntries(ps.map((p) => [p.id, p])))
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
    <>
      <Header />
      <div className="container">
        {error && <div className="banner error">Couldn't load your trips: {error}</div>}

        <div className="section-title">Your ledger</div>
        <div className="grid">
          <Link to="/everyday" className="card">
            <div className="card-cover everyday" />
            <div className="card-body">
              <div className="card-title">My Everyday</div>
              <div className="card-meta">Personal receipts, just for you</div>
            </div>
          </Link>
        </div>

        <div className="section-title">Trips</div>
        <div className="grid">
          <button className="card new" onClick={() => setCreating(true)}>
            <span className="plus">+</span>
            <span>New trip</span>
          </button>

          {trips.map((t) => (
            <Link key={t.id} to={'/trip/' + t.id} className="card">
              <div className="card-cover illustrated">
                <TripCover trip={t} />
              </div>
              <div className="card-body">
                <div className="card-title">{t.name}</div>
                <div className="card-meta">
                  <span className="avatar-stack">
                    {t.member_ids.slice(0, 4).map((id) => (
                      <Avatar key={id} persona={personas[id]} size={22} />
                    ))}
                  </span>
                  <span>{dateRange(t) || `${t.member_ids.length} member${t.member_ids.length === 1 ? '' : 's'}`}</span>
                </div>
              </div>
            </Link>
          ))}
        </div>

        {!loading && trips.length === 0 && (
          <div className="empty">
            <div className="big">🧾</div>
            No trips yet — start one and drop in your first receipt.
          </div>
        )}
      </div>

      {creating && (
        <CreateTripModal
          onClose={() => setCreating(false)}
          onCreated={(trip) => {
            setCreating(false)
            navigate('/trip/' + trip.id)
          }}
        />
      )}
    </>
  )
}
