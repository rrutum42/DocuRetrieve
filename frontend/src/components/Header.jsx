import { Link, useNavigate } from 'react-router-dom'
import { usePersona } from '../persona.jsx'
import Avatar from './Avatar.jsx'
import retriever from '../../resources/retriever.png'

export default function Header() {
  const { persona, clear } = usePersona()
  const navigate = useNavigate()

  function switchProfile() {
    clear()
    navigate('/start') // straight to the picker, not the marketing page
  }

  return (
    <header className="app-header">
      <Link to="/" className="brand">
        <img src={retriever} alt="" className="brand-dog" />
        Docu<span className="dot">Retriever</span>
      </Link>
      <div className="who">
        <Avatar persona={persona} size={32} />
        <span style={{ fontWeight: 600 }}>{persona?.name}</span>
        <button className="btn ghost" onClick={switchProfile} title="Switch profile">
          Switch
        </button>
      </div>
    </header>
  )
}
