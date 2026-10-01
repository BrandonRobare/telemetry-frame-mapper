import { describe, it, expect } from 'vitest'
import {
  NO_SURFACE_SAMPLER_REASON,
  NOT_GEOREFERENCED_REASON,
  SurfaceMeasurementUnavailableError,
  boundaryReferenceElevation,
  computeVolume,
  sampleProfile,
  surfaceMeasurementGate,
} from './measurementMath'
import type { GeoTransform } from '../../types/api'

// Simple sampler: flat surface at 10 m
const flatSampler = () => 10

// Sampler that returns null half the time
function sparseSampler(x: number): number | null {
  return Math.round(x * 10) % 2 === 0 ? 10 : null
}

const IDENTITY_GEO: GeoTransform = {
  scale: 1,
  rotation: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
  translation: [0, 0, 0],
  utm_zone: '17N',
  utm_origin: [500000, 3900000],
}

// One scene unit is two metres.
const SCALE_2_GEO: GeoTransform = { ...IDENTITY_GEO, scale: 2 }

const SQUARE_4 = [
  { x: 0, y: 0, z: 0 },
  { x: 4, y: 0, z: 0 },
  { x: 4, y: 0, z: 4 },
  { x: 0, y: 0, z: 4 },
]

describe('sampleProfile', () => {
  it('returns empty array for fewer than 2 points', () => {
    expect(sampleProfile([], flatSampler, IDENTITY_GEO)).toEqual([])
    expect(sampleProfile([{ x: 0, y: 0, z: 0 }], flatSampler, IDENTITY_GEO)).toEqual([])
  })

  it('samples a straight line segment', () => {
    const samples = sampleProfile(
      [{ x: 0, y: 0, z: 0 }, { x: 3, y: 0, z: 0 }],
      flatSampler,
      IDENTITY_GEO,
      1.0,
    )
    // 3m long, spacing 1m → 4 samples (0, 1, 2, 3m)
    expect(samples.length).toBe(4)
    expect(samples[0].distance_m).toBe(0)
    expect(samples[3].distance_m).toBe(3)
    samples.forEach((s) => {
      expect(s.elevation).toBe(10)
    })
  })

  it('handles null sampler returns', () => {
    const samples = sampleProfile(
      [{ x: 0, y: 0, z: 0 }, { x: 2, y: 0, z: 0 }],
      sparseSampler,
      IDENTITY_GEO,
      0.5,
    )
    const nullCount = samples.filter((s) => s.elevation === null).length
    expect(nullCount).toBeGreaterThan(0)
    const validCount = samples.filter((s) => s.elevation !== null).length
    expect(validCount).toBeGreaterThan(0)
  })

  it('attaches GPS from the geo-transform', () => {
    const samples = sampleProfile(
      [{ x: 0, y: 0, z: 0 }, { x: 1, y: 0, z: 0 }],
      flatSampler,
      IDENTITY_GEO,
      1.0,
    )
    samples.forEach((s) => {
      expect(s.lat).toBeGreaterThan(30)
      expect(s.lat).toBeLessThan(40)
      expect(s.lon).toBeGreaterThan(-90)
      expect(s.lon).toBeLessThan(-70)
    })
  })

  it('handles multi-segment polyline', () => {
    const samples = sampleProfile(
      [{ x: 0, y: 0, z: 0 }, { x: 2, y: 0, z: 0 }, { x: 2, y: 0, z: 2 }],
      flatSampler,
      IDENTITY_GEO,
      1.0,
    )
    // Segment 1: 2m → 3 samples (0, 1, 2)
    // Segment 2: 2m → 3 samples (2, 3, 4) but last point of seg1 == first of seg2
    // Total: 5 samples with distances 0,1,2,3,4
    expect(samples.length).toBe(5)
    expect(Math.abs(samples[4].distance_m - 4)).toBeLessThan(0.01)
    // Check Z changes in second segment
    expect(samples[2].z).toBeCloseTo(0, 5)
    expect(samples[3].z).toBeCloseTo(1, 5)
  })

  it('scales scene units by geo_transform.scale before reporting metres (#953)', () => {
    // 3 scene units at 2 m/unit is 6 m; 1 m spacing → 7 samples, not 4.
    const samples = sampleProfile(
      [{ x: 0, y: 0, z: 0 }, { x: 3, y: 0, z: 0 }],
      flatSampler,
      SCALE_2_GEO,
      1.0,
    )
    expect(samples.length).toBe(7)
    expect(samples[samples.length - 1].distance_m).toBeCloseTo(6, 9)
    expect(samples[1].x).toBeCloseTo(0.5, 9) // 1 m step is half a scene unit
  })

  it('refuses to sample without a surface sampler (#953)', () => {
    const line = [{ x: 0, y: 0, z: 0 }, { x: 3, y: 0, z: 0 }]
    expect(() => sampleProfile(line, null, IDENTITY_GEO)).toThrow(
      SurfaceMeasurementUnavailableError,
    )
    expect(() => sampleProfile(line, undefined, IDENTITY_GEO)).toThrow(NO_SURFACE_SAMPLER_REASON)
  })

  it('refuses to report metres for a reconstruction that is not georeferenced (#953)', () => {
    const line = [{ x: 0, y: 0, z: 0 }, { x: 3, y: 0, z: 0 }]
    expect(() => sampleProfile(line, flatSampler, undefined)).toThrow(NOT_GEOREFERENCED_REASON)
    expect(() => sampleProfile(line, flatSampler, { ...IDENTITY_GEO, utm_zone: 'unknown' }))
      .toThrow(NOT_GEOREFERENCED_REASON)
  })
})

describe('computeVolume', () => {
  it('returns zero for fewer than 3 polygon vertices', () => {
    const result = computeVolume([{ x: 0, y: 0, z: 0 }], flatSampler, 0, IDENTITY_GEO)
    expect(result.net_m3).toBe(0)
    expect(result.sampleCount).toBe(0)
  })

  it('computes volume of a flat quad above reference (all cut)', () => {
    // 4m × 4m square, surface at 12 m, reference=10 → 2m height diff
    const poly = [
      { x: 0, y: 12, z: 0 },
      { x: 4, y: 12, z: 0 },
      { x: 4, y: 12, z: 4 },
      { x: 0, y: 12, z: 4 },
    ]
    const sampler = () => 12
    const result = computeVolume(poly, sampler, 10, IDENTITY_GEO, 1.0)
    // Area = 16 m², height = 2m → volume = 32 m³
    expect(result.cut_m3).toBeCloseTo(32, 0)
    expect(result.fill_m3).toBe(0)
    expect(result.net_m3).toBeCloseTo(32, 0)
    expect(result.cut_yd3).toBeCloseTo(32 * 1.3079506193, 3)
    expect(result.sampleCount).toBe(16) // 4x4 grid at 1m spacing
    expect(result.referenceElevationM).toBe(10)
  })

  it('computes volume below reference (all fill)', () => {
    const poly = [
      { x: 0, y: 8, z: 0 },
      { x: 2, y: 8, z: 0 },
      { x: 2, y: 8, z: 2 },
      { x: 0, y: 8, z: 2 },
    ]
    const sampler = () => 8
    const result = computeVolume(poly, sampler, 10, IDENTITY_GEO, 0.5)
    // Area 4m², diff = -2m → fill = 8 m³
    expect(result.fill_m3).toBeCloseTo(8, 1)
    expect(result.cut_m3).toBeCloseTo(0, 1)
    expect(result.net_m3).toBeCloseTo(-8, 1)
  })

  it('handles mixed cut and fill', () => {
    // 2×2 square, sampler: left half at 12 m, right half at 8 m, ref=10
    const poly = [
      { x: 0, y: 0, z: 0 },
      { x: 2, y: 0, z: 0 },
      { x: 2, y: 0, z: 2 },
      { x: 0, y: 0, z: 2 },
    ]
    function mixedSampler(x: number): number {
      return x < 1 ? 12 : 8
    }
    const result = computeVolume(poly, mixedSampler, 10, IDENTITY_GEO, 1.0)
    // 4 cells, half at +2, half at -2 → cut=4, fill=4, net=0
    expect(result.cut_m3).toBeCloseTo(4, 1)
    expect(result.fill_m3).toBeCloseTo(4, 1)
    expect(Math.abs(result.net_m3)).toBeLessThan(0.01)
  })

  it('skips null sampler returns', () => {
    const poly = [
      { x: 0, y: 0, z: 0 },
      { x: 2, y: 0, z: 0 },
      { x: 2, y: 0, z: 2 },
      { x: 0, y: 0, z: 2 },
    ]
    function nullHalf(x: number): number | null {
      return x < 1 ? 12 : null
    }
    const result = computeVolume(poly, nullHalf, 10, IDENTITY_GEO, 0.5)
    // Only left half contributes
    expect(result.sampleCount).toBeGreaterThan(0)
    expect(result.sampleCount).toBeLessThan(16) // less than full grid
    expect(result.cut_m3).toBeGreaterThan(0)
    expect(result.fill_m3).toBe(0)
  })

  it('produces deterministic results repeated', () => {
    const poly = [
      { x: 0, y: 15, z: 0 },
      { x: 3, y: 15, z: 0 },
      { x: 3, y: 15, z: 3 },
      { x: 0, y: 15, z: 3 },
    ]
    const sampler = () => 15
    const r1 = computeVolume(poly, sampler, 10, IDENTITY_GEO, 0.5)
    const r2 = computeVolume(poly, sampler, 10, IDENTITY_GEO, 0.5)
    expect(r1).toEqual(r2)
  })

  it('handles non-axis-aligned triangles', () => {
    // Right triangle: (0,0), (4,0), (0,4) — area = 8
    const poly = [
      { x: 0, y: 12, z: 0 },
      { x: 4, y: 12, z: 0 },
      { x: 0, y: 12, z: 4 },
    ]
    const sampler = () => 12
    const result = computeVolume(poly, sampler, 10, IDENTITY_GEO, 0.5)
    // Area ≈ 8, height = 2 → ~16 m³. Center-cell raster sampling
    // undercounts diagonal polygon boundaries at coarse 0.5 m spacing.
    expect(result.net_m3).toBeGreaterThan(13)
    expect(result.net_m3).toBeLessThan(17)
    expect(result.sampleCount).toBeGreaterThan(25) // many samples on 0.5m grid
  })

  it('returns the analytic wedge volume for a sloped surface (#953)', () => {
    // 4×4 scene units at 2 m/unit is an 8 m × 8 m base. The surface rises
    // 0.5 m per scene unit along X, from the 0 m reference to 2 m at the far
    // edge: a wedge of ½ · 64 m² · 2 m = 64 m³. Midpoint sampling of a linear
    // surface over whole cells is exact.
    const slope = (x: number) => 0.5 * x
    const result = computeVolume(SQUARE_4, slope, 0, SCALE_2_GEO, 1.0)
    expect(result.cut_m3).toBeCloseTo(64, 9)
    expect(result.fill_m3).toBe(0)
    expect(result.cut_yd3).toBeCloseTo(64 * 1.3079506193, 6)
    expect(result.gridSpacingM).toBe(1.0)
    expect(result.sampleCount).toBe(64) // 8 × 8 one-metre cells
  })

  it('splits a sloped surface through the reference into equal cut and fill wedges', () => {
    // Surface z = x − 2 m over a 4 m square: +2 m wedge on one side, −2 m on the other.
    const result = computeVolume(SQUARE_4, (x) => x - 2, 0, IDENTITY_GEO, 1.0)
    expect(result.cut_m3).toBeCloseTo(8, 9)
    expect(result.fill_m3).toBeCloseTo(8, 9)
    expect(result.net_m3).toBeCloseTo(0, 9)
  })

  it('refuses to compute without a surface sampler (#953)', () => {
    expect(() => computeVolume(SQUARE_4, null, 0, IDENTITY_GEO)).toThrow(
      SurfaceMeasurementUnavailableError,
    )
    expect(() => computeVolume(SQUARE_4, undefined, 0, IDENTITY_GEO)).toThrow(
      NO_SURFACE_SAMPLER_REASON,
    )
  })

  it('refuses to report m³ for a reconstruction that is not georeferenced (#953)', () => {
    expect(() => computeVolume(SQUARE_4, flatSampler, 0, null)).toThrow(NOT_GEOREFERENCED_REASON)
    expect(() => computeVolume(SQUARE_4, flatSampler, 0, { ...IDENTITY_GEO, scale: 0 }))
      .toThrow(NOT_GEOREFERENCED_REASON)
  })
})

describe('boundaryReferenceElevation', () => {
  it('is the mean surface elevation at the polygon vertices', () => {
    // Vertices at x=0 sit at 10 m, vertices at x=4 at 14 m.
    expect(boundaryReferenceElevation(SQUARE_4, (x) => 10 + x)).toBe(12)
  })

  it('ignores vertices the surface has no height for', () => {
    expect(boundaryReferenceElevation(SQUARE_4, (x) => (x === 0 ? 10 : null))).toBe(10)
  })

  it('is null when no vertex has a surface height', () => {
    expect(boundaryReferenceElevation(SQUARE_4, () => null)).toBeNull()
  })
})

describe('surfaceMeasurementGate', () => {
  it('keeps profile and volume unavailable without a surface sampler (#953)', () => {
    const gate = surfaceMeasurementGate(null, IDENTITY_GEO)
    expect(gate.available).toBe(false)
    if (!gate.available) expect(gate.reason).toBe(NO_SURFACE_SAMPLER_REASON)
  })

  it('keeps profile and volume unavailable when the reconstruction is not georeferenced', () => {
    for (const geo of [undefined, null, { ...IDENTITY_GEO, utm_zone: 'unknown' }]) {
      const gate = surfaceMeasurementGate(flatSampler, geo)
      expect(gate.available).toBe(false)
      if (!gate.available) expect(gate.reason).toBe(NOT_GEOREFERENCED_REASON)
    }
  })

  it('reports the missing surface first when both prerequisites are missing', () => {
    const gate = surfaceMeasurementGate(null, undefined)
    expect(gate.available).toBe(false)
    if (!gate.available) expect(gate.reason).toBe(NO_SURFACE_SAMPLER_REASON)
  })

  it('is available with a real sampler and a georeferenced reconstruction', () => {
    const gate = surfaceMeasurementGate(flatSampler, SCALE_2_GEO)
    expect(gate.available).toBe(true)
    if (gate.available) {
      expect(gate.sampler).toBe(flatSampler)
      expect(gate.geo).toBe(SCALE_2_GEO)
      expect(gate.metresPerUnit).toBe(2)
    }
  })
})
