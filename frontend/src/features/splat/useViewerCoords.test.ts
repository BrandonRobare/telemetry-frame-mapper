// @vitest-environment jsdom
import { useRef } from 'react'
import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { deriveGroundPlaneY, worldToGps, gpsToWorld, useRayCast } from './useViewerCoords'
import type { GeoTransform } from '../../types/api'

const IDENTITY: GeoTransform = {
  scale: 1,
  rotation: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
  translation: [0, 0, 0],
  utm_zone: '17N',
  utm_origin: [500000, 3900000],
}

describe('worldToGps', () => {
  it('maps world origin to utm_origin lat/lon', () => {
    const result = worldToGps({ x: 0, y: 0, z: 0 }, IDENTITY)
    expect(result).not.toBeNull()
    // UTM zone 17N origin (500000E, 3900000N) maps to roughly lat ~35.2, lon ~-81.0
    // We don't assert exact values — just that we get finite numbers in range
    expect(result!.lat).toBeGreaterThan(30)
    expect(result!.lat).toBeLessThan(40)
    expect(result!.lon).toBeGreaterThan(-90)
    expect(result!.lon).toBeLessThan(-70)
    expect(result!.alt).toBeCloseTo(0, 5)
  })

  it('returns null for unknown utm_zone', () => {
    const geo: GeoTransform = { ...IDENTITY, utm_zone: 'unknown' }
    expect(worldToGps({ x: 0, y: 0, z: 0 }, geo)).toBeNull()
  })

  it('allows callers to fall back to scene-unit measurements for unknown utm_zone', () => {
    const geo: GeoTransform = { ...IDENTITY, utm_zone: 'unknown' }
    expect(worldToGps({ x: 3, y: 0, z: 4 }, geo)).toBeNull()
    expect(Math.hypot(3, 0, 4)).toBe(5)
  })

  it('offsets in world space shift lon/lat correctly', () => {
    const base = worldToGps({ x: 0, y: 0, z: 0 }, IDENTITY)!
    const east = worldToGps({ x: 1000, y: 0, z: 0 }, IDENTITY)!
    // +1000m easting → greater longitude
    expect(east.lon).toBeGreaterThan(base.lon)
    expect(east.lat).toBeCloseTo(base.lat, 2)
  })

  it('applies scale correctly', () => {
    const geo: GeoTransform = { ...IDENTITY, scale: 2 }
    const single = worldToGps({ x: 500, y: 0, z: 0 }, IDENTITY)!
    const scaled = worldToGps({ x: 500, y: 0, z: 0 }, geo)!
    // scale=2 means world x=500 maps to utm easting offset of 1000 → further east
    expect(scaled.lon).toBeGreaterThan(single.lon)
  })

  it('handles southern hemisphere (S zone)', () => {
    const geo: GeoTransform = { ...IDENTITY, utm_zone: '18S', utm_origin: [500000, 6000000] }
    const result = worldToGps({ x: 0, y: 0, z: 0 }, geo)
    expect(result).not.toBeNull()
    expect(result!.lat).toBeLessThan(0)
  })
})

describe('gpsToWorld', () => {
  it('round-trips worldToGps → gpsToWorld within float tolerance', () => {
    const world = { x: 123.45, y: 0, z: -67.89 }
    const gps = worldToGps(world, IDENTITY)!
    const back = gpsToWorld(gps, IDENTITY)!
    expect(back.x).toBeCloseTo(world.x, 3)
    expect(back.y).toBeCloseTo(world.y, 3)
    expect(back.z).toBeCloseTo(world.z, 3)
  })

  it('returns null for unknown utm_zone', () => {
    const geo: GeoTransform = { ...IDENTITY, utm_zone: 'unknown' }
    expect(gpsToWorld({ lat: 35, lon: -81, alt: 100 }, geo)).toBeNull()
  })

  it('round-trips at non-zero translation', () => {
    const geo: GeoTransform = { ...IDENTITY, translation: [100, 200, 50] }
    const world = { x: 50, y: 0, z: 30 }
    const gps = worldToGps(world, geo)!
    const back = gpsToWorld(gps, geo)!
    expect(back.x).toBeCloseTo(world.x, 3)
    expect(back.y).toBeCloseTo(world.y, 3)
    expect(back.z).toBeCloseTo(world.z, 3)
  })
})

describe('deriveGroundPlaneY', () => {
  it('derives the viewer Y plane from vertical translation', () => {
    expect(deriveGroundPlaneY({ ...IDENTITY, translation: [0, 0, 100], scale: 1 })).toBe(-100)
  })

  it('accounts for transform scale', () => {
    expect(deriveGroundPlaneY({ ...IDENTITY, translation: [0, 0, 200], scale: 2 })).toBe(-100)
  })

  it('falls back to zero when geo-transform metadata is missing', () => {
    expect(deriveGroundPlaneY(undefined)).toBe(0)
  })
})

// #664: SplatCanvas keeps `castRay` in the dependency array of the effect that
// wires the canvas click/dblclick listeners. An unmemoized `castRay` gets a new
// identity every render, so those listeners were torn down and re-attached on
// every render — which, while orbiting, is every pointer move.
describe('useRayCast', () => {
  function useSubject(groundY: number) {
    const viewerRef = useRef<unknown>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    return useRayCast(viewerRef, containerRef, groundY)
  }

  it('keeps castRay identity stable across re-renders', () => {
    const { result, rerender } = renderHook(({ groundY }) => useSubject(groundY), {
      initialProps: { groundY: 0 },
    })

    const first = result.current.castRay
    rerender({ groundY: 0 })
    rerender({ groundY: 0 })

    expect(result.current.castRay).toBe(first)
  })

  it('rebuilds castRay when the ground plane moves', () => {
    const { result, rerender } = renderHook(({ groundY }) => useSubject(groundY), {
      initialProps: { groundY: 0 },
    })

    const first = result.current.castRay
    rerender({ groundY: 12.5 })

    expect(result.current.castRay).not.toBe(first)
  })
})
