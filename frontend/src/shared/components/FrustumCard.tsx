import type { CSSProperties, ReactNode } from 'react'

interface FrustumCardProps {
  /** The near image plane — typically a frame thumbnail. */
  children: ReactNode
  className?: string
  style?: CSSProperties
  color?: string
  /** How far the far plane insets toward center, as a fraction (0..0.5). */
  inset?: number
  /** Line opacity — keep low so the photo behind stays readable. */
  opacity?: number
}

/* Frames content as a camera frustum: the child is the near image plane, a
   smaller far plane is drawn in one-point perspective with four connecting
   edges. The universal SfM camera-pose glyph, applied to actual frames. The
   overlay is decorative (pointer-events: none) and sits above the content. */
export function FrustumCard({
  children,
  className = '',
  style,
  color = 'var(--accent-strong)',
  inset = 0.26,
  opacity = 0.5,
}: FrustumCardProps) {
  const a = inset * 100
  const b = 100 - inset * 100
  return (
    <div className={`relative ${className}`.trim()} style={style}>
      {children}
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
      >
        <g fill="none" stroke={color} strokeWidth={0.75} opacity={opacity}>
          <rect x={a} y={a} width={b - a} height={b - a} vectorEffect="non-scaling-stroke" />
          <line x1="0" y1="0" x2={a} y2={a} vectorEffect="non-scaling-stroke" />
          <line x1="100" y1="0" x2={b} y2={a} vectorEffect="non-scaling-stroke" />
          <line x1="0" y1="100" x2={a} y2={b} vectorEffect="non-scaling-stroke" />
          <line x1="100" y1="100" x2={b} y2={b} vectorEffect="non-scaling-stroke" />
        </g>
      </svg>
    </div>
  )
}

/* A small standalone frustum glyph — the icon for "frames / camera poses".
   Nested squares (near + far plane) joined by four perspective edges. */
export function FrustumMark({ size = 16, color = 'var(--accent-strong)' }: { size?: number; color?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={1.3}
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ display: 'block', flexShrink: 0 }}
    >
      <rect x="3" y="4" width="18" height="16" />
      <rect x="8.5" y="9" width="7" height="6" opacity={0.6} />
      <line x1="3" y1="4" x2="8.5" y2="9" />
      <line x1="21" y1="4" x2="15.5" y2="9" />
      <line x1="3" y1="20" x2="8.5" y2="15" />
      <line x1="21" y1="20" x2="15.5" y2="15" />
    </svg>
  )
}

export default FrustumCard
