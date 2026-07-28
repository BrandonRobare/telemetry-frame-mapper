import { describe, expect, it } from 'vitest'
import { geoOriginLatLon } from './useViewerCoords'

/**
 * Split View opened on a hardcoded [35, -80] and only recentred once the 3D
 * camera published a viewport — so it showed satellite imagery ~680 km from an
 * Ohio reconstruction until the user happened to orbit.
 */
describe('geoOriginLatLon', () => {
  const ohio = {
    scale: 57.4367,
    rotation: [[1, 0, 0], [0, 1, 0], [0, 0, 1]] as [
      [number, number, number], [number, number, number], [number, number, number],
    ],
    translation: [0, 0, 0] as [number, number, number],
    utm_zone: '17N',
    utm_origin: [471617.1, 4555396.9] as [number, number],
  }

  it('maps the UTM origin back to the survey site', () => {
    const origin = geoOriginLatLon(ohio)
    expect(origin).not.toBeNull()
    expect(origin!.lat).toBeCloseTo(41.1509, 2)
    expect(origin!.lon).toBeCloseTo(-81.3382, 2)
  })

  it('is nowhere near the old hardcoded fallback', () => {
    const origin = geoOriginLatLon(ohio)!
    expect(Math.abs(origin.lat - 35.0)).toBeGreaterThan(5)
  })

  it('returns null without a solved geo-transform, so the caller can fall back', () => {
    expect(geoOriginLatLon(undefined)).toBeNull()
    expect(geoOriginLatLon(null)).toBeNull()
    expect(geoOriginLatLon({ ...ohio, utm_zone: 'unknown' })).toBeNull()
  })
})
