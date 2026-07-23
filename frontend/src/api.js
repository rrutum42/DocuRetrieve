// Thin API client. Persists the selected persona id and sends it as the
// X-Persona-Id header on every request — the server's visibility key.

const PERSONA_KEY = 'docuretrieve.personaId'

export function getPersonaId() {
  return localStorage.getItem(PERSONA_KEY)
}

export function setPersonaId(id) {
  if (id) localStorage.setItem(PERSONA_KEY, id)
  else localStorage.removeItem(PERSONA_KEY)
}

async function req(path, opts = {}) {
  const isForm = opts.body instanceof FormData
  // Let the browser set the multipart boundary for FormData; JSON otherwise.
  const headers = {
    ...(isForm ? {} : { 'Content-Type': 'application/json' }),
    ...(opts.headers || {}),
  }
  const pid = getPersonaId()
  if (pid) headers['X-Persona-Id'] = pid

  const res = await fetch('/api' + path, { ...opts, headers })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch {
      /* non-JSON error body */
    }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return res.status === 204 ? null : res.json()
}

export const api = {
  config: () => req('/config'),
  listPersonas: () => req('/personas'),
  createPersona: (name, color) =>
    req('/personas', { method: 'POST', body: JSON.stringify({ name, color }) }),
  listTrips: () => req('/trips'),
  createTrip: (trip) =>
    req('/trips', { method: 'POST', body: JSON.stringify(trip) }),
  getTrip: (id) => req('/trips/' + id),
  deleteTrip: (id) => req('/trips/' + id, { method: 'DELETE' }),
  addMembers: (id, memberIds) =>
    req('/trips/' + id + '/members', {
      method: 'POST',
      body: JSON.stringify({ member_ids: memberIds }),
    }),

  // Receipts
  extract: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return req('/extract', { method: 'POST', body: fd })
  },
  createReceipt: (payload, file) => {
    const fd = new FormData()
    fd.append('payload', JSON.stringify(payload))
    fd.append('file', file)
    return req('/receipts', { method: 'POST', body: fd })
  },
  listTripReceipts: (tripId) => req('/trips/' + tripId + '/receipts'),
  listPersonalReceipts: () => req('/receipts/personal'),
  deleteReceipt: (id) => req('/receipts/' + id, { method: 'DELETE' }),
  disputeReceipt: (id, reason) =>
    req('/receipts/' + id + '/dispute', {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  resolveDispute: (id) => req('/receipts/' + id + '/dispute', { method: 'DELETE' }),

  // Summaries & natural-language ask
  askTrip: (tripId, question) =>
    req('/trips/' + tripId + '/ask', {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
  askPersonal: (question) =>
    req('/receipts/personal/ask', {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
}

export const CATEGORIES = [
  'groceries',
  'dining',
  'fuel',
  'lodging',
  'transport',
  'shopping',
  'other',
]

// Currencies Frankfurter (ECB) can convert into — safe choices for a trip's
// base currency. Ordered with common travel currencies first.
export const CURRENCIES = [
  ['INR', '₹ Indian Rupee'],
  ['USD', '$ US Dollar'],
  ['EUR', '€ Euro'],
  ['GBP', '£ British Pound'],
  ['JPY', '¥ Japanese Yen'],
  ['AUD', 'A$ Australian Dollar'],
  ['CAD', 'C$ Canadian Dollar'],
  ['CHF', 'Swiss Franc'],
  ['CNY', '¥ Chinese Yuan'],
  ['SGD', 'S$ Singapore Dollar'],
  ['HKD', 'HK$ Hong Kong Dollar'],
  ['THB', '฿ Thai Baht'],
  ['NZD', 'NZ$ New Zealand Dollar'],
  ['ZAR', 'South African Rand'],
]
