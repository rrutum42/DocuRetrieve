// Natural-language ask, as a collapsible chat bubble. A launcher in the corner
// opens a floating panel that holds the conversation; each question and its
// answer stay on screen, and recent turns ride back with the next question so
// the planner can resolve a follow-up ("and on dining?"). The thread lives in
// sessionStorage (per container) so it survives navigation within a visit but
// isn't persisted server-side. Every answer still filters the ledger to the
// receipts behind it (onResult), so numbers stay traceable.

import { useEffect, useRef, useState } from 'react'
import { money } from '../format'
import retriever from '../../resources/retriever.png'

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

function AnswerCard({ result }) {
  const matched = result.matched?.length || 0
  return (
    <div className={'ask-answer' + (result.error ? ' ask-answer-error' : '')}>
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
      {matched > 0 && (
        <div className="ask-answer-foot">
          {matched} receipt{matched === 1 ? '' : 's'} behind this
        </div>
      )}
    </div>
  )
}

export default function AskBox({ ask, examples = [], storageKey }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  // The conversation: [{ question, result }], oldest first. A turn with
  // result === null is still awaiting its answer.
  const [turns, setTurns] = useState(() => loadThread(storageKey))
  const threadRef = useRef(null)
  const inputRef = useRef(null)

  // Reload the thread when the container changes (switching trips), and never
  // leak one container's conversation into another.
  useEffect(() => {
    setTurns(loadThread(storageKey))
  }, [storageKey])

  // Persist completed turns so a reload within the session keeps the thread.
  // Pending turns (result === null) are dropped — an in-flight question isn't
  // worth restoring.
  useEffect(() => {
    if (!storageKey) return
    try {
      const done = turns.filter((t) => t.result)
      sessionStorage.setItem(storageKey, JSON.stringify(done))
    } catch {
      /* storage full / unavailable — the in-memory thread still works */
    }
  }, [turns, storageKey])

  // Keep the latest turn in view and focus the input when the panel opens.
  useEffect(() => {
    if (!open) return
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight
    inputRef.current?.focus()
  }, [open, turns])

  async function run(question) {
    const text = (question ?? q).trim()
    if (!text || busy) return
    setBusy(true)
    // Build history from completed turns before we add the pending one.
    const history = turns
      .filter((t) => t.result)
      .slice(-HISTORY_TURNS)
      .map((t) => ({ question: t.question, answer: t.result.answer }))
    // Show the question immediately (result === null renders as "Thinking…");
    // the answer fills in when it arrives. Don't make the user wait to see it.
    setQ('')
    setTurns((prev) => [...prev, { question: text, result: null, pending: true }])
    try {
      const res = await ask(text, history)
      setTurns((prev) =>
        prev.map((t) => (t.pending ? { question: t.question, result: res } : t)),
      )
    } catch (e) {
      // Land the error in the thread, in place of the pending answer.
      setTurns((prev) =>
        prev.map((t) =>
          t.pending
            ? { question: t.question, result: { answer: e.message, matched: [], error: true } }
            : t,
        ),
      )
    } finally {
      setBusy(false)
    }
  }

  function clear() {
    setTurns([])
    setQ('')
    if (storageKey) sessionStorage.removeItem(storageKey)
  }

  return (
    <div className="askwidget">
      {open && (
        <div className="ask-panel" role="dialog" aria-label="Ask about your spending">
          <div className="ask-panel-head">
            <span className="ask-panel-title">
              <span className="ask-spark">✦</span> Ask about your spending
            </span>
            <div className="ask-panel-actions">
              {turns.length > 0 && (
                <button className="ask-panel-clear" onClick={clear} disabled={busy}>
                  Clear
                </button>
              )}
              <button
                className="ask-panel-close"
                onClick={() => setOpen(false)}
                aria-label="Close"
              >
                ✕
              </button>
            </div>
          </div>

          <div className="ask-thread" ref={threadRef}>
            {turns.length === 0 ? (
              <div className="ask-empty">
                <p>Ask anything about this ledger — totals, who paid, by category, settle-up. Follow-ups work too.</p>
                {examples.length > 0 && (
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
              </div>
            ) : (
              turns.map((t, i) => (
                <div key={i} className="ask-turn">
                  <div className="ask-question">{t.question}</div>
                  {t.result ? (
                    <AnswerCard result={t.result} />
                  ) : (
                    <div className="ask-typing">Thinking…</div>
                  )}
                </div>
              ))
            )}
          </div>

          <form
            className="ask-form"
            onSubmit={(e) => {
              e.preventDefault()
              run()
            }}
          >
            <input
              ref={inputRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                // Ask on Enter directly. Don't rely on implicit form submission:
                // the submit button is disabled while the field is empty, which
                // suppresses it in some browsers. (Ignore IME composition.)
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault()
                  run()
                }
              }}
              placeholder={turns.length > 0 ? 'Ask a follow-up…' : 'Ask a question…'}
              aria-label="Ask about your spending"
            />
            <button type="submit" className="btn primary" disabled={busy || !q.trim()}>
              Ask
            </button>
          </form>
        </div>
      )}

      {!open && (
        <button
          className="ask-fab"
          onClick={() => setOpen(true)}
          aria-expanded={false}
          aria-label="Open chat — ask about your spending"
        >
          <span className="ask-fab-cta">Click here to open chat</span>
          <span className="ask-fab-dog">
            <img src={retriever} alt="" />
          </span>
        </button>
      )}
    </div>
  )
}
