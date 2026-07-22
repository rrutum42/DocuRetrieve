// Current-persona context, backed by localStorage. This is the "no real auth,
// just a profile you pick" model — the whole app reads who you are from here.

import { createContext, useContext, useEffect, useState } from 'react'
import { api, getPersonaId, setPersonaId } from './api'

const PersonaContext = createContext(null)

export function PersonaProvider({ children }) {
  const [persona, setPersona] = useState(null)
  const [loading, setLoading] = useState(true)

  // On load / refresh we only have the stored id — rehydrate the full persona
  // object by matching it against the roster so a reload keeps you signed in.
  useEffect(() => {
    const id = getPersonaId()
    if (!id) {
      setLoading(false)
      return
    }
    api
      .listPersonas()
      .then((people) => {
        const found = people.find((p) => p.id === id)
        if (found) setPersona(found)
        else setPersonaId(null) // stale id — force reselect
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  function choose(p) {
    setPersona(p)
    setPersonaId(p ? p.id : null)
  }

  function clear() {
    setPersona(null)
    setPersonaId(null)
  }

  return (
    <PersonaContext.Provider value={{ persona, loading, choose, clear }}>
      {children}
    </PersonaContext.Provider>
  )
}

export function usePersona() {
  return useContext(PersonaContext)
}
