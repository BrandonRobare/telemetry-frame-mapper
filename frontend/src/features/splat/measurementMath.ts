import type { GeoTransform } from '../../types/api'
import { metresPerSceneUnit, worldToGps } from './useViewerCoords'

// ---------------------------------------------------------------------------
// Shared measurement math — pure functions for profile sampling & volume.
//
// Both tools report surface heights in metres, so they need two things this
// module refuses to fake (#953):
//   * a real surface sampler — heights read from the reconstructed surface
//     (a DSM or point-cloud height query), never a constant ground plane; and
//   * a georeferenced reconstruction — scene units only become metres once
//     scaled by geo_transform.scale.
// surfaceMeasurementGate() says whether both are present; sampleProfile() and
// computeVolume() throw SurfaceMeasurementUnavailableError when they are not.
// ---------------------------------------------------------------------------

export interface WorldPoint3 {
  x: number
  y: number
  z: number
}

/**
 * Surface elevation in metres at a scene-space (x, z) position, or null where
 * the surface has no data. It must read the reconstructed surface: a constant
 * or ground-plane function is not a surface sampler.
 */
export type SurfaceSampler = (x: number, z: number) => number | null

export const NO_SURFACE_SAMPLER_REASON =
  'Profile and volume are off: the viewer has no surface-height source (DSM or point cloud) ' +
  'to sample yet.'

export const NOT_GEOREFERENCED_REASON =
  'Profile and volume are off: this reconstruction is not georeferenced, so heights and ' +
  'distances cannot be given in metres.'

export class SurfaceMeasurementUnavailableError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'SurfaceMeasurementUnavailableError'
  }
}

export type SurfaceMeasurementGate =
  | { available: true; sampler: SurfaceSampler; geo: GeoTransform; metresPerUnit: number }
  | { available: false; reason: string }

/** Whether profile and volume can run, and if not, a short reason to show the user. */
export function surfaceMeasurementGate(
  sampler: SurfaceSampler | null | undefined,
  geo: GeoTransform | null | undefined,
): SurfaceMeasurementGate {
  if (typeof sampler !== 'function') return { available: false, reason: NO_SURFACE_SAMPLER_REASON }
  const metresPerUnit = metresPerSceneUnit(geo)
  if (!geo || metresPerUnit === null) return { available: false, reason: NOT_GEOREFERENCED_REASON }
  return { available: true, sampler, geo, metresPerUnit }
}

function requireSurface(
  sampler: SurfaceSampler | null | undefined,
  geo: GeoTransform | null | undefined,
) {
  const gate = surfaceMeasurementGate(sampler, geo)
  if (!gate.available) throw new SurfaceMeasurementUnavailableError(gate.reason)
  return gate
}

function requirePositive(name: string, value: number): void {
  // A zero step never advances the sampling loops below.
  if (!Number.isFinite(value) || value <= 0) {
    throw new RangeError(`${name} must be a finite value greater than zero`)
  }
}

// ---------------------------------------------------------------------------
// Profile sampling
// ---------------------------------------------------------------------------

export interface ProfileSample {
  /** Cumulative distance along the polyline in metres (scene distance × geo scale) */
  distance_m: number
  /** World X */
  x: number
  /** World Z */
  z: number
  /** Surface elevation in metres from the sampler (null where the surface has no data) */
  elevation: number | null
  /** GPS lat from the geo-transform */
  lat: number | null
  /** GPS lon */
  lon: number | null
}

export function sampleProfile(
  points: readonly WorldPoint3[],
  sampler: SurfaceSampler | null | undefined,
  geo: GeoTransform | null | undefined,
  sampleSpacingM = 0.5,
): ProfileSample[] {
  const surface = requireSurface(sampler, geo)
  requirePositive('sampleSpacingM', sampleSpacingM)
  if (points.length < 2) return []

  const samples: ProfileSample[] = []
  let cumulativeDistanceM = 0

  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i]
    const b = points[i + 1]
    const dx = b.x - a.x
    const dy = b.y - a.y
    const dz = b.z - a.z
    const segLenM = Math.sqrt(dx * dx + dz * dz) * surface.metresPerUnit
    const steps = Math.max(1, Math.round(segLenM / sampleSpacingM))

    for (let s = i === 0 ? 0 : 1; s <= steps; s++) {
      const t = s / steps
      const wx = a.x + dx * t
      const wz = a.z + dz * t
      const gps = worldToGps({ x: wx, y: a.y + dy * t, z: wz }, surface.geo)

      samples.push({
        distance_m: cumulativeDistanceM + segLenM * t,
        x: wx,
        z: wz,
        elevation: surface.sampler(wx, wz),
        lat: gps?.lat ?? null,
        lon: gps?.lon ?? null,
      })
    }

    cumulativeDistanceM += segLenM
  }

  return samples
}

// ---------------------------------------------------------------------------
// Volume (cut/fill) calculation
// ---------------------------------------------------------------------------

export interface VolumeResult {
  /** Volume above reference (cut) in m³ */
  cut_m3: number
  /** Volume below reference (fill) in m³ */
  fill_m3: number
  /** Net volume (cut - fill) in m³ */
  net_m3: number
  /** Cut in yd³ */
  cut_yd3: number
  /** Fill in yd³ */
  fill_yd3: number
  /** Net in yd³ */
  net_yd3: number
  /** Number of grid cells with valid surface samples */
  sampleCount: number
  /** Grid spacing used (m) */
  gridSpacingM: number
  /** Base elevation the cut and fill are measured from (m) */
  referenceElevationM: number
}

const M3_TO_YD3 = 1.3079506193

/**
 * Compute cut/fill volume by sampling a grid within the polygon.
 *
 * The polygon is defined by its vertices (world-space XZ). Each grid cell is
 * tested for polygon containment; if contained, the sampler is queried at the
 * cell center.  Height difference = surface elevation − referenceElevationM.
 * Positive → cut (above reference), negative → fill (below reference).
 *
 * @param polygon    polygon vertices, assumed planar in XZ
 * @param sampler    real surface sampler: (x, z) → elevation (m) or null
 * @param referenceElevationM  flat base elevation (m); extension point for
 *                            second surface via a different sampler
 * @param geo        geo-transform; its scale converts scene units to metres
 * @param gridSpacingM  grid cell size in metres (default 0.5)
 */
export function computeVolume(
  polygon: readonly WorldPoint3[],
  sampler: SurfaceSampler | null | undefined,
  referenceElevationM: number,
  geo: GeoTransform | null | undefined,
  gridSpacingM = 0.5,
): VolumeResult {
  const surface = requireSurface(sampler, geo)
  requirePositive('gridSpacingM', gridSpacingM)
  if (!Number.isFinite(referenceElevationM)) {
    throw new RangeError('referenceElevationM must be a finite value')
  }
  if (polygon.length < 3) {
    return {
      cut_m3: 0, fill_m3: 0, net_m3: 0, cut_yd3: 0, fill_yd3: 0, net_yd3: 0,
      sampleCount: 0, gridSpacingM, referenceElevationM,
    }
  }

  // Bounding box
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity
  for (const p of polygon) {
    if (p.x < minX) minX = p.x
    if (p.x > maxX) maxX = p.x
    if (p.z < minZ) minZ = p.z
    if (p.z > maxZ) maxZ = p.z
  }

  // Precompute polygon edges for even-odd ray casting
  type Edge = { x1: number; z1: number; x2: number; z2: number }
  const edges: Edge[] = []
  for (let i = 0; i < polygon.length; i++) {
    const a = polygon[i]
    const b = polygon[(i + 1) % polygon.length]
    edges.push({ x1: a.x, z1: a.z, x2: b.x, z2: b.z })
  }

  function pointInPolygon(px: number, pz: number): boolean {
    let inside = false
    for (const e of edges) {
      // Ray cast: horizontal ray to the right
      if ((e.z1 > pz) !== (e.z2 > pz)) {
        const xIntersect = e.x1 + ((pz - e.z1) * (e.x2 - e.x1)) / (e.z2 - e.z1)
        if (px < xIntersect) inside = !inside
      }
    }
    return inside
  }

  let cut = 0
  let fill = 0
  let sampleCount = 0
  const cellArea = gridSpacingM * gridSpacingM
  // The polygon is in scene units; step the grid in scene units that span
  // gridSpacingM metres so each cell covers cellArea square metres.
  const step = gridSpacingM / surface.metresPerUnit

  // Iterate grid cells using center-point sampling
  // Offset by half grid spacing so samples are cell centers
  for (let gx = minX + step / 2; gx <= maxX; gx += step) {
    for (let gz = minZ + step / 2; gz <= maxZ; gz += step) {
      if (!pointInPolygon(gx, gz)) continue
      const sy = surface.sampler(gx, gz)
      if (sy === null) continue
      const diff = sy - referenceElevationM
      if (diff > 0) cut += diff * cellArea
      else fill += -diff * cellArea
      sampleCount++
    }
  }

  return {
    cut_m3: cut,
    fill_m3: fill,
    net_m3: cut - fill,
    cut_yd3: cut * M3_TO_YD3,
    fill_yd3: fill * M3_TO_YD3,
    net_yd3: (cut - fill) * M3_TO_YD3,
    sampleCount,
    gridSpacingM,
    referenceElevationM,
  }
}

/**
 * Mean surface elevation (m) at the polygon's vertices — the base plane cut and
 * fill are measured from — or null when the surface has no height at any vertex.
 */
export function boundaryReferenceElevation(
  polygon: readonly WorldPoint3[],
  sampler: SurfaceSampler,
): number | null {
  const heights = polygon
    .map((p) => sampler(p.x, p.z))
    .filter((h): h is number => h !== null)
  if (heights.length === 0) return null
  return heights.reduce((sum, h) => sum + h, 0) / heights.length
}
