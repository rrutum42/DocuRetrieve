// Illustrated cover for the personal "My Everyday" ledger — a busy work desk,
// in the same flat, self-contained SVG style as the trip covers (TripCover.jsx).

export default function EverydayCover() {
  return (
    <svg
      className="trip-cover-svg"
      viewBox="0 0 320 128"
      preserveAspectRatio="xMidYMid slice"
      role="img"
      aria-label="a busy work desk"
    >
      <defs>
        <linearGradient id="everyday-wall" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f1e8dc" />
          <stop offset="1" stopColor="#e0d0bb" />
        </linearGradient>
      </defs>
      <rect width="320" height="128" fill="url(#everyday-wall)" />

      {/* sticky notes pinned to the wall */}
      <rect x="34" y="18" width="26" height="24" rx="2" fill="#f2cf63" transform="rotate(-5 47 30)" />
      <rect x="70" y="22" width="24" height="22" rx="2" fill="#8fc7a0" transform="rotate(4 82 33)" />

      {/* desk surface */}
      <rect y="96" width="320" height="32" fill="#b98b5e" />
      <rect y="96" width="320" height="5" fill="#a97b4f" />

      {/* stacked papers / receipts */}
      <rect x="50" y="84" width="46" height="16" rx="2" fill="#efe7db" transform="rotate(-7 73 92)" />
      <rect x="55" y="82" width="46" height="16" rx="2" fill="#fbf7f0" transform="rotate(4 78 90)" />
      <rect x="60" y="86" width="30" height="2.4" rx="1" fill="#cabda8" transform="rotate(4 75 87)" />
      <rect x="60" y="90" width="24" height="2.4" rx="1" fill="#cabda8" transform="rotate(4 72 91)" />

      {/* pen */}
      <rect x="44" y="75" width="34" height="4" rx="2" fill="#4a7a4a" transform="rotate(-14 61 77)" />
      <path d="M43 83 l5 -3 l1 3 z" fill="#33582f" />

      {/* laptop */}
      <rect x="122" y="56" width="74" height="44" rx="4" fill="#463f4f" />
      <rect x="127" y="61" width="64" height="34" rx="2" fill="#8fb9cc" />
      <rect x="140" y="69" width="38" height="3" rx="1.5" fill="#d6e6ee" opacity="0.85" />
      <rect x="140" y="76" width="30" height="3" rx="1.5" fill="#d6e6ee" opacity="0.6" />
      <rect x="140" y="83" width="34" height="3" rx="1.5" fill="#d6e6ee" opacity="0.6" />
      <rect x="108" y="99" width="100" height="6" rx="3" fill="#372f3d" />

      {/* coffee mug with a little steam */}
      <path
        d="M216 71 q2 -6 0 -11 M224 71 q2 -6 0 -11"
        fill="none"
        stroke="#d9c8b4"
        strokeWidth="2"
        opacity="0.7"
      />
      <path d="M232 82 h6 a5 5 0 0 1 0 10 h-6" fill="none" stroke="#c4603d" strokeWidth="3.5" />
      <rect x="208" y="80" width="26" height="18" rx="3" fill="#c4603d" />
      <ellipse cx="221" cy="80" rx="13" ry="3.5" fill="#e7d8c6" />

      {/* little desk plant */}
      <rect x="256" y="82" width="18" height="16" rx="2" fill="#b5714a" />
      <path d="M265 82 q-7 -15 1 -22 q7 8 -1 22" fill="#4a9d6b" />
      <path d="M266 85 q10 -9 18 -7 q-6 10 -18 7" fill="#57ab77" />
    </svg>
  )
}
