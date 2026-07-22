import { Navigate, Route, Routes } from 'react-router-dom'
import { usePersona } from './persona.jsx'
import PersonaPicker from './screens/PersonaPicker.jsx'
import Home from './screens/Home.jsx'
import TripView from './screens/TripView.jsx'

export default function App() {
  const { persona, loading } = usePersona()

  if (loading) {
    return <div className="spinner">Loading…</div>
  }

  // No persona selected → the picker owns the whole screen.
  if (!persona) {
    return <PersonaPicker />
  }

  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/trip/:id" element={<TripView />} />
      <Route path="/everyday" element={<TripView everyday />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
