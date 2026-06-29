interface CornerTicksProps {
  color?: string
  /** Tick arm length in px. */
  size?: number
  /** Offset from the corner; negative sits on the border line. */
  inset?: number
  /** Optional faint mono registration readout, pinned bottom-right (e.g. a
      session name or coordinate). Survey-plate flavor; keep it short + truthful. */
  label?: string
}

/* Four L-shaped registration ticks at the corners of a framed surface — the
   technical-drawing accent. The parent must be `position: relative`. */
export function CornerTicks({ color = 'var(--accent-strong)', size = 8, inset = -1, label }: CornerTicksProps) {
  const base: React.CSSProperties = { position: 'absolute', width: size, height: size, borderColor: color, borderStyle: 'solid', pointerEvents: 'none' }
  return (
    <>
      <span aria-hidden="true" style={{ ...base, top: inset, left: inset, borderWidth: '1.5px 0 0 1.5px' }} />
      <span aria-hidden="true" style={{ ...base, top: inset, right: inset, borderWidth: '1.5px 1.5px 0 0' }} />
      <span aria-hidden="true" style={{ ...base, bottom: inset, left: inset, borderWidth: '0 0 1.5px 1.5px' }} />
      <span aria-hidden="true" style={{ ...base, bottom: inset, right: inset, borderWidth: '0 1.5px 1.5px 0' }} />
      {label && (
        <span
          aria-hidden="true"
          style={{
            position: 'absolute', bottom: 5, right: 10,
            fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '0.1em',
            color: 'var(--text-faint)', textTransform: 'uppercase', pointerEvents: 'none',
            maxWidth: '55%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
        >
          {label}
        </span>
      )}
    </>
  )
}

export default CornerTicks
