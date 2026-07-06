import { describe, it, expect } from 'vitest'
import { sampleProfile, computeVolume } from './measurementMath'
import type { GeoTransform } from '../../types/api'

// Simple sampler: flat surface at Y=10
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

describe('sampleProfile', () => {
  it('returns empty array for fewer than 2 points', () => {
    expect(sampleProfile([], flatSampler)).toEqual([])
    expect(sampleProfile([{ x: 0, y: 0, z: 0 }], flatSampler)).toEqual([])
  })

  it('samples a straight line segment', () => {
    const samples = sampleProfile(
      [{ x: 0, y: 0, z: 0 }, { x: 3, y: 0, z: 0 }],
      flatSampler,
      1.0,
    )
    // 3m long, spacing 1m → 4 samples (0, 1, 2, 3m)
    expect(samples.length).toBe(4)
    expect(samples[0].distance_m).toBe(0)
    expect(samples[3].distance_m).toBe(3)
    samples.forEach((s) => {
      expect(s.elevation).toBe(10)
      expect(s.lat).toBeNull() // no geo
    })
  })

  it('handles null sampler returns', () => {
    const samples = sampleProfile(
      [{ x: 0, y: 0, z: 0 }, { x: 2, y: 0, z: 0 }],
      sparseSampler,
      0.5,
    )
    const nullCount = samples.filter((s) => s.elevation === null).length
    expect(nullCount).toBeGreaterThan(0)
    const validCount = samples.filter((s) => s.elevation !== null).length
    expect(validCount).toBeGreaterThan(0)
  })

  it('attaches GPS when geo-transform is provided', () => {
    const samples = sampleProfile(
      [{ x: 0, y: 0, z: 0 }, { x: 1, y: 0, z: 0 }],
      flatSampler,
      1.0,
      IDENTITY_GEO,
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
})

describe('computeVolume', () => {
  it('returns zero for fewer than 3 polygon vertices', () => {
    const result = computeVolume([{ x: 0, y: 0, z: 0 }], flatSampler, 0)
    expect(result.net_m3).toBe(0)
    expect(result.sampleCount).toBe(0)
  })

  it('computes volume of a flat quad above reference (all cut)', () => {
    // 4m × 4m square, surface at Y=12, reference=10 → 2m height diff
    const poly = [
      { x: 0, y: 12, z: 0 },
      { x: 4, y: 12, z: 0 },
      { x: 4, y: 12, z: 4 },
      { x: 0, y: 12, z: 4 },
    ]
    const sampler = () => 12
    const result = computeVolume(poly, sampler, 10, 1.0)
    // Area = 16 m², height = 2m → volume = 32 m³
    expect(result.cut_m3).toBeCloseTo(32, 0)
    expect(result.fill_m3).toBe(0)
    expect(result.net_m3).toBeCloseTo(32, 0)
    expect(result.cut_yd3).toBeCloseTo(32 * 1.3079506193, 3)
    expect(result.sampleCount).toBe(16) // 4x4 grid at 1m spacing
  })

  it('computes volume below reference (all fill)', () => {
    const poly = [
      { x: 0, y: 8, z: 0 },
      { x: 2, y: 8, z: 0 },
      { x: 2, y: 8, z: 2 },
      { x: 0, y: 8, z: 2 },
    ]
    const sampler = () => 8
    const result = computeVolume(poly, sampler, 10, 0.5)
    // Area 4m², diff = -2m → fill = 8 m³
    expect(result.fill_m3).toBeCloseTo(8, 1)
    expect(result.cut_m3).toBeCloseTo(0, 1)
    expect(result.net_m3).toBeCloseTo(-8, 1)
  })

  it('handles mixed cut and fill', () => {
    // 2×2 square, sampler: left half at Y=12, right half at Y=8, ref=10
    const poly = [
      { x: 0, y: 0, z: 0 },
      { x: 2, y: 0, z: 0 },
      { x: 2, y: 0, z: 2 },
      { x: 0, y: 0, z: 2 },
    ]
    function mixedSampler(x: number): number {
      return x < 1 ? 12 : 8
    }
    const result = computeVolume(poly, mixedSampler, 10, 1.0)
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
    const result = computeVolume(poly, nullHalf, 10, 0.5)
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
    const r1 = computeVolume(poly, sampler, 10, 0.5)
    const r2 = computeVolume(poly, sampler, 10, 0.5)
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
    const result = computeVolume(poly, sampler, 10, 0.5)
    // Area ≈ 8, height = 2 → ~16 m³. Center-cell raster sampling
    // undercounts diagonal polygon boundaries at coarse 0.5 m spacing.
    expect(result.net_m3).toBeGreaterThan(13)
    expect(result.net_m3).toBeLessThan(17)
    expect(result.sampleCount).toBeGreaterThan(25) // many samples on 0.5m grid
  })
})