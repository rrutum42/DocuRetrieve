import { Navigate, Route, Routes } from 'react-router-dom'
import { usePersona } from './persona.jsx'
import Landing from './screens/Landing.jsx'
import PersonaPicker from './screens/PersonaPicker.jsx'
import Home from './screens/Home.jsx'
import TripView from './screens/TripView.jsx'

export default function App() {
  const { persona, loading } = usePersona()

  if (loading) {
    return <div className="spinner">Loading…</div>
  }

  // Logged out → the public landing page at "/", the profile picker at "/start".
  if (!persona) {
    return (
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/start" element={<PersonaPicker />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/welcome" element={<Landing />} />
      <Route path="/trip/:id" element={<TripView />} />
      <Route path="/everyday" element={<TripView everyday />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
