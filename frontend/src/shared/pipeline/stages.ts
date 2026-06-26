// Pipeline source of truth for drone-survey stages, state derivation, and stage colors.
import type { Session, Reconstruction, Job, CoverageResult } from '../../types/api'

export type StageKey = 'import' | 'review' | 'align' | 'train' | 'view' | 'export'
export type StageState = 'pending' | 'active' | 'done' | 'failed'

export interface PipelineStage {
  key: StageKey
  name: string
  icon: string // Tabler icon name WITHOUT the 'ti-' prefix, e.g. 'upload'
  description: string // one sentence: what this step does
  tab: string
}

export const PIPELINE_STAGES: PipelineStage[] = [
  {
    key: 'import',
    name: 'Import',
    icon: 'upload',
    tab: 'map',
    description: 'Ingest geotagged frames from a DJI flight; read GPS and altitude per frame.',
  },
  {
    key: 'review',
    name: 'Review',
    icon: 'checks',
    tab: 'review',
    description: 'Flag blurry, dark, or no-GPS frames and pick the usable set.',
  },
  {
    key: 'align',
    name: 'Align',
    icon: 'affiliate',
    tab: 'reconstruct',
    description: "COLMAP structure-from-motion solves each frame's camera pose.",
  },
  {
    key: 'train',
    name: 'Train',
    icon: 'box',
    tab: 'reconstruct',
    description: 'Gaussian-splat training builds the 3D reconstruction.',
  },
  {
    key: 'view',
    name: 'View',
    icon: 'eye',
    tab: 'splat',
    description: 'Explore the reconstruction in 3D; measure, annotate, and find coverage gaps.',
  },
  {
    key: 'export',
    name: 'Export',
    icon: 'download',
    tab: 'export',
    description: 'Output an orthophoto, point cloud, mesh, or flythrough video.',
  },
]

// Stage status colors — kept as literal hex (not CSS vars) because they feed
// Three.js materials in HexPrismLogo3D, which can't resolve var(). They mirror
// --tan / --accent / --sage / --danger-accent in index.css — keep in sync.
const STAGE_COLORS: Record<StageState, string> = {
  pending: '#C4A484',
  active: '#B87C4C',
  done: '#A8BBA3',
  failed: '#B5503C',
}

export function deriveStageStates(input: {
  session?: Session | null
  reconstruction?: Reconstruction | Job | null
  coverage?: CoverageResult | null
}): Record<StageKey, StageState> {
  const { session, reconstruction } = input

  if (!session) {
    return {
      import: 'active',
      review: 'pending',
      align: 'pending',
      train: 'pending',
      view: 'pending',
      export: 'pending',
    }
  }

  const reconstructionStatus = reconstruction?.status
  const done: Record<StageKey, boolean> = {
    import: session.photo_count > 0,
    review: session.usable_count > 0,
    align: reconstructionStatus === 'running_gsplat' || reconstructionStatus === 'complete',
    train: reconstructionStatus === 'complete',
    view: reconstructionStatus === 'complete',
    export: false,
  }

  const activeStageKey = PIPELINE_STAGES.find((stage) => !done[stage.key])?.key ?? 'export'
  const stateForActiveStage: StageState = reconstructionStatus === 'failed' ? 'failed' : 'active'
  const states: Record<StageKey, StageState> = {
    import: 'pending',
    review: 'pending',
    align: 'pending',
    train: 'pending',
    view: 'pending',
    export: 'pending',
  }

  let reachedActiveStage = false

  for (const stage of PIPELINE_STAGES) {
    if (stage.key === activeStageKey) {
      states[stage.key] = stateForActiveStage
      reachedActiveStage = true
      continue
    }

    states[stage.key] = reachedActiveStage ? 'pending' : 'done'
  }

  return states
}

export function stageColor(state: StageState): string {
  return STAGE_COLORS[state]
}

// --- Logo motion: maps live pipeline state to the visual scalars shared by the
// 2D splat-trio LogoMark and the 3D ReconstructionLogo3D, so they stay in sync.

export interface LogoMotion {
  /** 0..1 — how far points have moved from scatter to their terrain target. */
  organization: number
  /** 0..1 — splat size / softness (peaks during Train). */
  bloom: number
  /** 0..1 — terrain landform resolve (View/Export). */
  solid: number
  /** Index of the active stage in PIPELINE_STAGES, or -1 if none is active. */
  activeIndex: number
  failed: boolean
}

// Keyframes indexed by number of completed stages (0..6). Validated in the
// interactive concept mockups during design.
const ORG_KEYS = [0.04, 0.12, 0.45, 0.82, 0.95, 1.0, 1.0]
const BLOOM_KEYS = [0.18, 0.22, 0.45, 1.0, 0.72, 0.58, 0.5]
const SOLID_KEYS = [0.0, 0.0, 0.12, 0.35, 0.7, 0.95, 1.0]

export function deriveLogoMotion(states: Record<StageKey, StageState>): LogoMotion {
  let doneCount = 0
  let activeIndex = -1
  let failed = false
  PIPELINE_STAGES.forEach((stage, i) => {
    const st = states[stage.key]
    if (st === 'done') doneCount += 1
    if (st === 'active' && activeIndex === -1) activeIndex = i
    if (st === 'failed') failed = true
  })
  const idx = Math.max(0, Math.min(6, doneCount))
  return {
    organization: ORG_KEYS[idx],
    bloom: BLOOM_KEYS[idx],
    solid: SOLID_KEYS[idx],
    activeIndex,
    failed,
  }
}

// Stage ramp tan → amber → sage as organization climbs 0→1. Literal rgb (not CSS
// vars) so the 2D reactive trio and the 3D cloud (which can't resolve var())
// render the same colors. Mirrors --tan / amber / --sage.
const RAMP_TAN = '#C4A484'
const RAMP_AMBER = '#C8902F'
const RAMP_SAGE = '#A8BBA3'

function rampLerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}
function rampHex(h: string): [number, number, number] {
  return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)]
}
function rampMix(c1: string, c2: string, t: number): string {
  const a = rampHex(c1)
  const b = rampHex(c2)
  return `rgb(${Math.round(rampLerp(a[0], b[0], t))}, ${Math.round(rampLerp(a[1], b[1], t))}, ${Math.round(rampLerp(a[2], b[2], t))})`
}

export function logoRampColor(o: number): string {
  const c = Math.max(0, Math.min(1, o))
  return c < 0.5 ? rampMix(RAMP_TAN, RAMP_AMBER, c / 0.5) : rampMix(RAMP_AMBER, RAMP_SAGE, (c - 0.5) / 0.5)
}
