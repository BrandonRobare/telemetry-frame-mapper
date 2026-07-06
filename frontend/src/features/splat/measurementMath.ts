import type { GeoTransform } from '../../types/api'
import { worldToGps } from '../splat/useViewerCoords'

// ---------------------------------------------------------------------------
// Shared measurement math — pure functions for profile sampling & volume.
// All surface sampling passes through the same sampling interface so callers
// can swap between mesh hits, splat query, or flat ground plane.
// ---------------------------------------------------------------------------

export interface WorldPoint3 {
  x: number
  y: number
  z: number
}

export type SurfaceSampler = (x: number, z: number) => number | null

// ---------------------------------------------------------------------------
// Profile sampling
// ---------------------------------------------------------------------------

export interface ProfileSample {
  /** Cumulative distance along the polyline (m) */
  distance_m: number
  /** World X */
  x: number
  /** World Z */
  z: number
  /** Sampled surface elevation Y (null if sampler returned null) */
  elevation: number | null
  /** GPS lat, if geo-transform available */
  lat: number | null
  /** GPS lon */
  lon: number | null
}

export function sampleProfile(
  points: readonly WorldPoint3[],
  sampler: SurfaceSampler,
  sampleSpacingM = 0.5,
  geo?: GeoTransform,
): ProfileSample[] {
  if (points.length < 2) return []

  const samples: ProfileSample[] = []
  let cumulativeDistance = 0

  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i]
    const b = points[i + 1]
    const dx = b.x - a.x
    const dz = b.z - a.z
    const segLen = Math.sqrt(dx * dx + dz * dz)
    const steps = Math.max(1, Math.round(segLen / sampleSpacingM))

    for (let s = i === 0 ? 0 : 1; s <= steps; s++) {
      const t = s / steps
      const wx = a.x + dx * t
      const wz = a.z + dz * t
      const wy = sampler(wx, wz)
      const segDist = segLen * t
      const gps = geo ? worldToGps({ x: wx, y: wy ?? 0, z: wz }, geo) : null

      samples.push({
        distance_m: cumulativeDistance + segDist,
        x: wx,
        z: wz,
        elevation: wy,
        lat: gps?.lat ?? null,
        lon: gps?.lon ?? null,
      })
    }

    cumulativeDistance += segLen
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
}

const M3_TO_YD3 = 1.3079506193

/**
 * Compute cut/fill volume by sampling a grid within the polygon.
 *
 * The polygon is defined by its vertices (world-space XZ). Each grid cell is
 * tested for polygon containment; if contained, the sampler is queried at the
 * cell center.  Height difference = surfaceY − referenceElevation.
 * Positive → cut (above reference), negative → fill (below reference).
 *
 * @param polygon    polygon vertices, assumed planar in XZ
 * @param sampler    surface sampler: (x, z) → y or null
 * @param referenceElevation  flat base elevation (m); extension point for
 *                            second surface via a different sampler
 * @param gridSpacingM  grid cell size in meters (default 0.5)
 */
export function computeVolume(
  polygon: readonly WorldPoint3[],
  sampler: SurfaceSampler,
  referenceElevation: number,
  gridSpacingM = 0.5,
): VolumeResult {
  if (polygon.length < 3) {
    return { cut_m3: 0, fill_m3: 0, net_m3: 0, cut_yd3: 0, fill_yd3: 0, net_yd3: 0, sampleCount: 0, gridSpacingM }
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

  // Iterate grid cells using center-point sampling
  // Offset by half grid spacing so samples are cell centers
  for (let gx = minX + gridSpacingM / 2; gx <= maxX; gx += gridSpacingM) {
    for (let gz = minZ + gridSpacingM / 2; gz <= maxZ; gz += gridSpacingM) {
      if (!pointInPolygon(gx, gz)) continue
      const sy = sampler(gx, gz)
      if (sy === null) continue
      const diff = sy - referenceElevation
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
  }
}