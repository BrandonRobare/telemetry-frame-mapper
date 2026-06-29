import type { CSSProperties } from 'react'
import { generatePoints, POINT_COLORS } from './pointFieldData'

export interface PointFieldProps {
  /** Number of points to scatter. */
  count?: number
  /** PRNG seed — same seed, same layout. */
  seed?: number
  /** Fraction of points shown (0..1) — lets the field "densify" with progress. */
  density?: number
  /** `drift` = ambient parallax twinkle; `reconstruct` = sparse→dense build loop. */
  animate?: 'none' | 'drift' | 'reconstruct'
  className?: string
  style?: CSSProperties
}

/* A point-cloud field — the project's foundational texture. The background
   literally is a sparse reconstruction. Renders an absolute SVG layer that
   fills its (position: relative) parent; decorative, never interactive. */
export function PointField({
  count = 120,
  seed = 7,
  density = 1,
  animate = 'none',
  className = '',
  style,
}: PointFieldProps) {
  const points = generatePoints(count, seed)
  const shown = Math.max(0, Math.min(count, Math.round(count * density)))
  const animClass = animate !== 'none' ? `fm-pointfield--${animate}` : ''

  return (
    <svg
      className={`fm-pointfield ${animClass} ${className}`.trim()}
      viewBox="0 0 100 100"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', ...style }}
    >
      {points.slice(0, shown).map((p, i) => (
        <circle
          key={i}
          cx={p.x}
          cy={p.y}
          r={p.r}
          fill={POINT_COLORS[p.c]}
          opacity={p.o}
          style={animate === 'reconstruct' ? { animationDelay: `${((i / shown) * 1.2).toFixed(3)}s` } : undefined}
        />
      ))}
    </svg>
  )
}

export default PointField
