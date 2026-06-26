import { deriveLogoMotion, logoRampColor } from '../pipeline/stages'
import type { StageKey, StageState } from '../pipeline/stages'

interface LogoMarkProps {
  /** Rendered px size (square). */
  size?: number
  /** When provided, the splat trio tints (tan→amber→sage) and pulses to track
      live pipeline state. Omitted = the static brand mark. */
  stageStates?: Record<StageKey, StageState>
  title?: string
}

/* Telemetry Frame Mapper identity: a "splat trio" — three soft gaussian lozenges
   around a benchmark core, the same material as the 3D ReconstructionLogo3D hero
   at a smaller zoom. Static = brand variant (theme-aware CSS vars); with
   stageStates it tints via logoRampColor, scales with bloom, pulses on the active
   stage, and flares brick on failure (see deriveLogoMotion). */

const BRICK = '#B5503C'
const CORE = '#9A5E32'

export function LogoMark({ size = 22, stageStates, title = 'Telemetry Frame Mapper' }: LogoMarkProps) {
  const m = stageStates ? deriveLogoMotion(stageStates) : null

  // Three lozenge fills. Static brand uses theme-aware CSS vars; reactive uses the
  // literal stage ramp at three slightly offset organization values for variety.
  const fills: [string, string, string] = m
    ? m.failed
      ? [BRICK, BRICK, BRICK]
      : [
          logoRampColor(m.organization + 0.12),
          logoRampColor(m.organization),
          logoRampColor(m.organization - 0.15),
        ]
    : ['var(--accent)', 'var(--sage)', 'var(--tan)']

  const coreFill = m ? (m.failed ? BRICK : CORE) : 'var(--accent-strong)'
  const scale = m ? 0.82 + m.bloom * 0.3 : 1
  const pulse = !!m && m.activeIndex >= 0 && !m.failed

  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" role="img" aria-label={title}>
      <title>{title}</title>
      <g transform={`translate(12 12) scale(${scale.toFixed(3)}) translate(-12 -12)`}>
        <g className={pulse ? 'fm-trio-pulse' : undefined}>
          <ellipse cx="10.5" cy="13" rx="6.2" ry="4.2" fill={fills[0]} opacity="0.85" />
          <ellipse
            cx="14"
            cy="10.5"
            rx="4.8"
            ry="6"
            fill={fills[1]}
            opacity="0.8"
            transform="rotate(18 14 10.5)"
          />
          <ellipse cx="11.8" cy="12" rx="3.2" ry="3" fill={fills[2]} opacity="0.92" />
          <circle cx="12" cy="12" r="1.8" fill={coreFill} />
        </g>
      </g>
    </svg>
  )
}

export default LogoMark
