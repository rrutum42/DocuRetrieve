import { Link } from 'react-router-dom'
import { usePersona } from '../persona.jsx'
import Avatar from './Avatar.jsx'

export default function Header() {
  const { persona, clear } = usePersona()
  return (
    <header className="app-header">
      <Link to="/" className="brand">
        Docu<span className="dot">Retrieve</span>
      </Link>
      <div className="who">
        <Avatar persona={persona} size={32} />
        <span style={{ fontWeight: 600 }}>{persona?.name}</span>
        <button className="btn ghost" onClick={clear} title="Switch profile">
          Switch
        </button>
      </div>
    </header>
  )
}
