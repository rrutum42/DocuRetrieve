// A small heads-up that the app runs on free hosting (cold starts + rate limits).

export default function FreeTierNote() {
  return (
    <div className="freetier-note">
      🐌 Heads up: everything here is hosted on a free tier. The first load after
      a while can be slow to wake up, and the AI receipt reader has a small daily
      limit — so give it a moment if things feel sluggish.
    </div>
  )
}
