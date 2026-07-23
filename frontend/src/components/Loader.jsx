// A proper animated loader — used everywhere instead of bare "Loading…" text.
// `full` centers it in the viewport (app boot); otherwise it sits inline.

export default function Loader({ label = 'Fetching…', full = false }) {
  return (
    <div className={full ? 'loader loader-full' : 'loader'}>
      <span className="loader-spinner" aria-hidden="true" />
      {label && <span className="loader-label">{label}</span>}
    </div>
  )
}
