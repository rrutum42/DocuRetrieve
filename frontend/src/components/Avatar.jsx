// A simple circular avatar: colored disc with the persona's initial.

const PALETTE = [
  '#c4603d', '#3d7cc4', '#4a9d6b', '#b6893d', '#8a5cc4', '#c43d6e', '#3daec4',
]

export function colorFor(persona) {
  if (persona?.color) return persona.color
  // Deterministic fallback from the name so avatars are stable.
  const name = persona?.name || '?'
  let h = 0
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % PALETTE.length
  return PALETTE[h]
}

export const AVATAR_PALETTE = PALETTE

export default function Avatar({ persona, size = 44 }) {
  const initial = (persona?.name || '?').trim().charAt(0).toUpperCase()
  return (
    <span
      className="avatar"
      title={persona?.name}
      style={{
        width: size,
        height: size,
        background: colorFor(persona),
        fontSize: size * 0.42,
      }}
    >
      {initial}
    </span>
  )
}
