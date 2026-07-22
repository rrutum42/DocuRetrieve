// Illustrated vacation-scene covers for trip cards. Self-contained inline SVGs
// (no external assets — works offline and in the CSP'd deploy).
//
// Theme selection: match keywords in the trip name first (so "Bali" looks like
// an island and "Paris" like a city), then fall back to a deterministic pick
// from the trip id so untitled/unmatched trips still vary.

const THEME_ORDER = ['beach', 'island', 'mountain', 'city', 'forest', 'desert']

const KEYWORDS = {
  island: ['island', 'maldives', 'bali', 'hawaii', 'tropic', 'fiji', 'caribbean', 'bahama'],
  beach: ['beach', 'coast', 'goa', 'miami', 'sea', 'ocean', 'shore', 'surf', 'cancun'],
  mountain: ['mountain', 'alp', 'ski', 'snow', 'himalaya', 'tahoe', 'aspen', 'peak', 'trek', 'hike'],
  city: ['city', 'paris', 'france', 'london', 'tokyo', 'york', 'nyc', 'rome', 'berlin', 'dubai', 'urban', 'town'],
  forest: ['forest', 'wood', 'camp', 'jungle', 'safari', 'national park', 'trail', 'nature'],
  desert: ['desert', 'sahara', 'arizona', 'canyon', 'dune', 'vegas', 'nevada'],
}

function hash(str) {
  let h = 0
  for (const ch of str || '') h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return h
}

export function themeFor(trip) {
  const name = (trip?.name || '').toLowerCase()
  for (const [theme, words] of Object.entries(KEYWORDS)) {
    if (words.some((w) => name.includes(w))) return theme
  }
  return THEME_ORDER[hash(trip?.id || trip?.name || '') % THEME_ORDER.length]
}

const SCENES = {
  beach: (id) => (
    <>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffd9a8" />
          <stop offset="1" stopColor="#9fd3e0" />
        </linearGradient>
      </defs>
      <rect width="320" height="128" fill={`url(#${id})`} />
      <circle cx="252" cy="40" r="18" fill="#ffb765" />
      <rect y="82" width="320" height="20" fill="#63b7c9" />
      <path d="M0 100 Q80 92 160 100 T320 100 V128 H0 Z" fill="#f2d7a6" />
      <path d="M40 100 q-6-26 4-40 q-14 6-18 16 q10-6 14-2 q-8 10-4 26Z" fill="#4a8a53" />
    </>
  ),
  island: (id) => (
    <>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#bfe8f2" />
          <stop offset="1" stopColor="#4aa7c4" />
        </linearGradient>
      </defs>
      <rect width="320" height="128" fill={`url(#${id})`} />
      <circle cx="60" cy="34" r="15" fill="#fff2c9" opacity="0.9" />
      <ellipse cx="180" cy="104" rx="86" ry="20" fill="#e9cfa0" />
      <path d="M180 92 q-4-22 4-34 q-13 5-17 15 q9-6 13-2 q-7 9-4 21Z" fill="#3f8a55" />
      <path d="M180 92 q10-18 26-22 q-8-6 -20 0 q6 2 4 8 q-8 4-10 14Z" fill="#4c9a60" />
    </>
  ),
  mountain: (id) => (
    <>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#cfe3f0" />
          <stop offset="1" stopColor="#8fb0c9" />
        </linearGradient>
      </defs>
      <rect width="320" height="128" fill={`url(#${id})`} />
      <circle cx="250" cy="36" r="14" fill="#fbf3df" />
      <path d="M-10 128 L70 52 L130 110 L150 90 L210 128 Z" fill="#7d95ac" />
      <path d="M130 128 L210 44 L300 128 Z" fill="#5f7891" />
      <path d="M210 44 L188 74 L200 78 L196 88 L224 80 L232 74 Z" fill="#f4f7fb" />
      <path d="M70 52 L56 74 L66 76 L62 84 L84 78 Z" fill="#f4f7fb" />
    </>
  ),
  city: (id) => (
    <>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f6c19a" />
          <stop offset="1" stopColor="#7c6b9e" />
        </linearGradient>
      </defs>
      <rect width="320" height="128" fill={`url(#${id})`} />
      <circle cx="70" cy="44" r="16" fill="#ffd9a0" opacity="0.85" />
      <g fill="#4a4363">
        <rect x="30" y="74" width="30" height="54" />
        <rect x="66" y="58" width="26" height="70" />
        <rect x="98" y="86" width="24" height="42" />
        <rect x="128" y="46" width="30" height="82" />
        <rect x="164" y="70" width="26" height="58" />
        <rect x="196" y="56" width="28" height="72" />
        <rect x="230" y="82" width="24" height="46" />
        <rect x="260" y="64" width="30" height="64" />
      </g>
      <g fill="#ffe9b8" opacity="0.7">
        <rect x="136" y="56" width="4" height="6" />
        <rect x="146" y="56" width="4" height="6" />
        <rect x="72" y="68" width="4" height="6" />
        <rect x="204" y="66" width="4" height="6" />
      </g>
    </>
  ),
  forest: (id) => (
    <>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#d7ead0" />
          <stop offset="1" stopColor="#7fae82" />
        </linearGradient>
      </defs>
      <rect width="320" height="128" fill={`url(#${id})`} />
      <circle cx="248" cy="40" r="14" fill="#fbf3df" />
      <g fill="#3f7a4e">
        {[20, 70, 118, 168, 214, 262].map((x, i) => (
          <path key={i} d={`M${x} 128 L${x + 22} 60 L${x + 44} 128 Z`} opacity={i % 2 ? 0.85 : 1} />
        ))}
      </g>
      <g fill="#2f5f3d">
        {[-6, 44, 92, 144, 190, 240, 292].map((x, i) => (
          <path key={i} d={`M${x} 128 L${x + 24} 78 L${x + 48} 128 Z`} />
        ))}
      </g>
    </>
  ),
  desert: (id) => (
    <>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffd39b" />
          <stop offset="1" stopColor="#e79a5c" />
        </linearGradient>
      </defs>
      <rect width="320" height="128" fill={`url(#${id})`} />
      <circle cx="240" cy="42" r="18" fill="#ffefb0" />
      <path d="M0 98 Q90 78 190 98 T320 92 V128 H0 Z" fill="#e9b072" />
      <path d="M0 128 Q120 104 220 122 T320 112 V128 Z" fill="#d69457" />
      <g fill="#4f7a4a">
        <rect x="48" y="86" width="8" height="34" rx="4" />
        <rect x="40" y="96" width="8" height="16" rx="4" />
        <rect x="56" y="92" width="8" height="18" rx="4" />
      </g>
    </>
  ),
}

export default function TripCover({ trip }) {
  const theme = themeFor(trip)
  const uid = `sky-${theme}-${(trip?.id || '0').slice(0, 8)}`
  return (
    <svg
      className="trip-cover-svg"
      viewBox="0 0 320 128"
      preserveAspectRatio="xMidYMid slice"
      role="img"
      aria-label={`${theme} scene`}
    >
      {SCENES[theme](uid)}
    </svg>
  )
}
