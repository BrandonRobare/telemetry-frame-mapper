// Pure logic for the Splat Viewer's presentation/narration mode.
//
// Camera-path interpolation is shared with the flythrough preview in
// SplatViewerTab.tsx (same keyframe shape, same easing contract as the
// server-side renderer — see smoothstep.ts) so presentation playback and the
// existing flythrough preview never drift apart.
//
// Keyframes are ad-hoc, user-captured camera stops (no natural "next slide"
// semantics), while annotations are independent GPS-pinned points with no
// ordering. That shape favors proximity-triggered narration callouts over a
// fixed slide deck: as the camera flies the existing keyframe path,
// `selectNarrationCallout` decides which nearby annotation (if any) to show.

export interface PresentationKeyframe {
  position: readonly [number, number, number]
  target: readonly [number, number, number]
  duration_s: number
}

export function lerpVec3(
  a: readonly [number, number, number],
  b: readonly [number, number, number],
  t: number,
): [number, number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
}

export function interpolateKeyframes(
  current: PresentationKeyframe,
  next: PresentationKeyframe,
  ease: number,
): { position: [number, number, number]; target: [number, number, number] } {
  return {
    position: lerpVec3(current.position, next.position, ease),
    target: lerpVec3(current.target, next.target, ease),
  }
}

/** Segment duration in ms, scaled by playback speed and floored at `minMs` (matches the flythrough preview's floor). */
export function scaledSegmentDurationMs(durationS: number, speed: number, minMs = 250): number {
  const safeSpeed = speed > 0 ? speed : 1
  return Math.max(minMs, (durationS * 1000) / safeSpeed)
}

/** Clamped step to the previous/next keyframe index — used by the prev/next arrow-key controls. */
export function stepKeyframeIndex(current: number, direction: 1 | -1, keyframeCount: number): number {
  if (keyframeCount <= 0) return 0
  return Math.max(0, Math.min(keyframeCount - 1, current + direction))
}

export const PRESENTATION_SPEEDS = [0.5, 1, 1.5, 2] as const
export type PresentationSpeed = (typeof PRESENTATION_SPEEDS)[number]

/** Cycles the playback speed forward/backward through PRESENTATION_SPEEDS, wrapping at both ends. */
export function cycleSpeed(current: number, direction: 1 | -1): number {
  const idx = PRESENTATION_SPEEDS.indexOf(current as PresentationSpeed)
  const base = idx === -1 ? PRESENTATION_SPEEDS.indexOf(1) : idx
  const next = (base + direction + PRESENTATION_SPEEDS.length) % PRESENTATION_SPEEDS.length
  return PRESENTATION_SPEEDS[next]
}

export function distance3(a: readonly [number, number, number], b: readonly [number, number, number]): number {
  const dx = a[0] - b[0]
  const dy = a[1] - b[1]
  const dz = a[2] - b[2]
  return Math.sqrt(dx * dx + dy * dy + dz * dz)
}

export interface NarrationPoint {
  id: number
  position: readonly [number, number, number]
}

/**
 * Choose which annotation (if any) to show as a narration callout, given the
 * camera's current world position.
 *
 * Uses hysteresis to avoid flicker: once a point becomes the active callout
 * it stays active until the camera passes `exitThresholdM` (default 1.5x
 * `enterThresholdM`), unless a different point is both in range and strictly
 * closer, in which case it takes over immediately.
 */
export function selectNarrationCallout<T extends NarrationPoint>(
  cameraPos: readonly [number, number, number],
  points: readonly T[],
  currentId: number | null,
  enterThresholdM: number,
  exitThresholdM: number = enterThresholdM * 1.5,
): T | null {
  if (points.length === 0) return null

  let nearest: T | null = null
  let nearestDist = Infinity
  for (const p of points) {
    const d = distance3(cameraPos, p.position)
    if (d < nearestDist) {
      nearest = p
      nearestDist = d
    }
  }

  const current = currentId != null ? points.find((p) => p.id === currentId) ?? null : null
  if (current) {
    const currentDist = distance3(cameraPos, current.position)
    const closerReplacementInRange =
      nearest !== null && nearest.id !== current.id && nearestDist < currentDist && nearestDist <= enterThresholdM
    if (currentDist <= exitThresholdM && !closerReplacementInRange) {
      return current
    }
  }

  return nearest && nearestDist <= enterThresholdM ? nearest : null
}
