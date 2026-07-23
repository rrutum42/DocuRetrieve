// Reusable confirmation dialog — replaces the browser's native confirm() with a
// styled, on-brand modal. Handles its own busy/error state while the confirm
// action runs, so callers just pass an async onConfirm.

import { useState } from 'react'

export default function ConfirmModal({
  title,
  message,
  confirmLabel = 'Delete',
  cancelLabel = 'Cancel',
  danger = true,
  onConfirm,
  onClose,
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      await onConfirm()
      // onConfirm is expected to close/navigate on success.
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={busy ? undefined : onClose}>
      <div
        className="modal confirm"
        onClick={(e) => e.stopPropagation()}
        role="alertdialog"
        aria-modal="true"
      >
        <h2>{title}</h2>
        {message && <p className="confirm-message">{message}</p>}
        {error && <div className="banner error">{error}</div>}
        <div className="modal-actions">
          <button className="btn ghost" onClick={onClose} disabled={busy}>
            {cancelLabel}
          </button>
          <button
            className={'btn ' + (danger ? 'danger' : 'primary')}
            onClick={confirm}
            disabled={busy}
            autoFocus
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
