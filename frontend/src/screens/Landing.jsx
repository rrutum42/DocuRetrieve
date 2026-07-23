// Public landing page: what DocuRetriever is and the journey through it.
// Shown to visitors before they pick a profile.

import { Link } from 'react-router-dom'
import retriever from '../../resources/retriever.png'

const STEPS = [
  {
    n: 1,
    title: 'Pick your profile',
    body: 'Choose who you are — like profiles on a shared device. No passwords, no sign-up.',
  },
  {
    n: 2,
    title: 'Start a trip, invite the crew',
    body: 'Group spending into trips (like photo albums) and add the people who are along for it.',
  },
  {
    n: 3,
    title: 'Snap a receipt',
    body: 'Photograph it — crumpled, blurry, handwritten, foreign currency. The retriever reads it into clean fields.',
  },
  {
    n: 4,
    title: 'Review & confirm',
    body: 'Glance at what it read, fix anything it flagged, and save. It checks the maths so wrong numbers get caught.',
  },
  {
    n: 5,
    title: 'See who paid & just ask',
    body: 'Get a per-person “who paid” split and settle-up — then ask “how much on dining in Goa?” in plain English.',
  },
]

const LIMITS = [
  [
    'Runs on a free AI tier',
    'The receipt reader allows roughly 20 automatic reads per day. Hit the limit and you can still add receipts by hand, or come back tomorrow.',
  ],
  [
    'Profiles, not real accounts',
    'You pick who you are — no passwords. It’s built for trusted family and friends sharing a space, not strangers on the internet.',
  ],
  [
    'Always confirm the numbers',
    'It reads even messy receipts well, but complex bills (utilities, telecom, handwriting) can occasionally pick the wrong total — so nothing saves until you review it.',
  ],
  [
    'Flags fakes, can’t prove them',
    'It marks suspiciously sparse receipts and lets trip members dispute anything that looks off — but no app can fully prove a photo is a genuine receipt.',
  ],
  [
    'Reference exchange rates',
    'Foreign amounts are converted using daily ECB reference rates for the receipt’s date — close, but not your card’s exact rate.',
  ],
]

export default function Landing() {
  return (
    <div className="landing">
      <header className="landing-nav">
        <div className="brand">
          <img src={retriever} alt="" className="brand-dog" />
          Docu<span className="dot">Retriever</span>
        </div>
        <Link to="/start" className="btn primary">
          Get started
        </Link>
      </header>

      <section className="hero">
        <img src={retriever} alt="A golden retriever" className="hero-dog" />
        <h1>
          Snap your receipts.<br />
          Let the retriever <span className="hl">fetch the answers.</span>
        </h1>
        <p className="hero-sub">
          A trip-first expense ledger for families and friends. Photograph any
          receipt — even the crumpled, handwritten, foreign-currency ones — and
          DocuRetriever turns your shoebox into a clean ledger you can actually ask
          questions of.
        </p>
        <div className="hero-cta">
          <Link to="/start" className="btn primary big">
            Get started — it’s free
          </Link>
          <span className="hero-note">No sign-up. Pick a profile and go.</span>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>How it works</h2>
          <p>From a photo to an answer in five steps.</p>
        </div>
        <ol className="steps">
          {STEPS.map((s) => (
            <li key={s.n} className="step">
              <span className="step-n">{s.n}</span>
              <div>
                <div className="step-title">{s.title}</div>
                <div className="step-body">{s.body}</div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Good to know</h2>
          <p>Honest about what it does — and what it doesn’t.</p>
        </div>
        <div className="limits">
          {LIMITS.map(([title, body]) => (
            <div key={title} className="limit">
              <div className="limit-title">{title}</div>
              <div className="limit-body">{body}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="cta-band">
        <img src={retriever} alt="" className="cta-dog" />
        <h2>Ready to put the shoebox down?</h2>
        <Link to="/start" className="btn primary big">
          Get started
        </Link>
      </section>

      <footer className="landing-foot">
        <span>
          Docu<span className="dot">Retriever</span>
        </span>
        <span className="foot-note">
          Built as a receipt-to-structured-data project. Snap → read → ask.
        </span>
      </footer>
    </div>
  )
}
