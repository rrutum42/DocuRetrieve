// Natural-language ask, as a conversation. Each question and its answer stay on
// screen as a thread, and the recent turns are sent back with the next question
// so the planner can resolve a follow-up ("and on dining?"). The thread lives in
// sessionStorage (per container), so it survives navigation within a visit but
// isn't persisted server-side. Every answer still links to the receipts behind
// it via onResult, so numbers stay traceable.

import { useEffect, useRef, useState } from 'react'
import { money } from '../format'

// How many recent turns to send as context. Bounded to keep the prompt small
// (the server also caps history length defensively).
const HISTORY_TURNS = 6

function loadThread(storageKey) {
  if (!storageKey) return []
  try {
    return JSON.parse(sessionStorage.getItem(storageKey)) || []
  } catch {
    return []
  }
}

function AnswerCard({ result, onSelect }) {
  const matched = result.matched?.length || 0
  return (
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
        {matched > 0 ? (
          <button className="ask-evidence" onClick={() => onSelect(result)}>
            Show the {matched} receipt{matched === 1 ? '' : 's'} behind this
          </button>
        ) : (
          <span>No matching receipts</span>
        )}
      </div>
    </div>
  )
}

export default function AskBox({ ask, onResult, examples = [], storageKey }) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  // The conversation: [{ question, result }], oldest first.
  const [turns, setTurns] = useState(() => loadThread(storageKey))
  const threadRef = useRef(null)

  // Reload the thread when the container changes (switching trips), and never
  // leak one container's conversation into another.
  useEffect(() => {
    setTurns(loadThread(storageKey))
    setError(null)
    onResult?.(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey])

  // Persist after every change so a reload within the session keeps the thread.
  useEffect(() => {
    if (!storageKey) return
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(turns))
    } catch {
      /* storage full / unavailable — the in-memory thread still works */
    }
    // keep the latest turn in view
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight
  }, [turns, storageKey])

  async function run(question) {
    const text = (question ?? q).trim()
    if (!text || busy) return
    setBusy(true)
    setError(null)
    const history = turns
      .slice(-HISTORY_TURNS)
      .map((t) => ({ question: t.question, answer: t.result.answer }))
    try {
      const res = await ask(text, history)
      setTurns((prev) => [...prev, { question: text, result: res }])
      setQ('')
      onResult?.(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  function clear() {
    setTurns([])
    setQ('')
    setError(null)
    if (storageKey) sessionStorage.removeItem(storageKey)
    onResult?.(null)
  }

  return (
    <div className="askbox">
      {turns.length > 0 && (
        <div className="ask-thread" ref={threadRef}>
          {turns.map((t, i) => (
            <div key={i} className="ask-turn">
              <div className="ask-question">{t.question}</div>
              <AnswerCard result={t.result} onSelect={onResult} />
            </div>
          ))}
        </div>
      )}

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
          placeholder={
            turns.length > 0 ? 'Ask a follow-up…' : 'Ask about your spending…'
          }
          aria-label="Ask about your spending"
        />
        <button type="submit" className="btn primary" disabled={busy || !q.trim()}>
          {busy ? 'Thinking…' : 'Ask'}
        </button>
        {turns.length > 0 && (
          <button
            type="button"
            className="btn ghost"
            onClick={clear}
            disabled={busy}
          >
            Clear
          </button>
        )}
      </form>

      {examples.length > 0 && turns.length === 0 && (
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
    </div>
  )
}
