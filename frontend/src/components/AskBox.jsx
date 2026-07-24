// Natural-language ask box. Submits a question, shows the answer sentence, and
// (via onResult) lets the parent filter the ledger down to the receipts behind
// the answer — so every number is traceable to its evidence.

import { useState } from 'react'
import { money } from '../format'

export default function AskBox({ ask, onResult, examples = [] }) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  async function run(question) {
    const text = (question ?? q).trim()
    if (!text || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await ask(text)
      setResult(res)
      onResult?.(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  function clear() {
    setResult(null)
    setQ('')
    onResult?.(null)
  }

  return (
    <div className="askbox">
      <form
        className="ask-form"
        onSubmit={(e) => {
          e.preventDefault()
          run()
        }}
      >
        <span className="ask-spark">✦</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask about your spending…"
          aria-label="Ask about your spending"
        />
        <button type="submit" className="btn primary" disabled={busy || !q.trim()}>
          {busy ? 'Thinking…' : 'Ask'}
        </button>
      </form>

      {examples.length > 0 && !result && (
        <div className="ask-examples">
          {examples.map((ex) => (
            <button
              key={ex}
              className="ask-chip"
              onClick={() => {
                setQ(ex)
                run(ex)
              }}
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      {error && <div className="banner error">{error}</div>}

      {result && (
        <div className="ask-answer">
          <div className="ask-answer-text">{result.answer}</div>
          {result.breakdown?.length > 0 && (
            <ul className="ask-breakdown">
              {result.breakdown.map((row) => (
                <li key={row.label} className="ask-breakdown-row">
                  <span className="ask-breakdown-label">{row.label}</span>
                  <span className="ask-breakdown-count">
                    {row.count} receipt{row.count === 1 ? '' : 's'}
                    {row.share > 0 && ` · ${Math.round(row.share)}%`}
                  </span>
                  <span className="ask-breakdown-value">
                    {money(row.value, row.currency)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="ask-answer-foot">
            {result.matched.length > 0
              ? `Showing the ${result.matched.length} receipt${
                  result.matched.length === 1 ? '' : 's'
                } behind this`
              : 'No matching receipts'}
            <button className="btn ghost" onClick={clear}>
              Clear
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
