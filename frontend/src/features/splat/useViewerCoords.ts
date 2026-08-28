import { useCallback } from 'react'
import type { RefObject } from 'react'
import proj4 from 'proj4'
import type { GeoTransform } from '../../types/api'

// ---------------------------------------------------------------------------
// Coordinate math: COLMAP world space ↔ GPS (WGS-84)
//
// The geo_transform stored on Reconstruction describes how to map from
// COLMAP world coordinates (P_world) to UTM:
//   P_utm = scale * (rotation @ P_world) + translation + [utm_origin[0], utm_origin[1], 0]
// UTM ↔ WGS-84 is handled by proj4.
// ---------------------------------------------------------------------------

interface GpsPoint {
  lat: number
  lon: number
  alt: number
}

interface WorldPoint {
  x: number
  y: number
  z: number
}

function parseUtmZone(utmZone: string): { zone: number; north: boolean } | null {
  const m = utmZone.match(/^(\d+)([NS])$/i)
  if (!m) return null
  return { zone: parseInt(m[1], 10), north: m[2].toUpperCase() === 'N' }
}

function utmToLatLon(
  easting: number,
  northing: number,
  zone: number,
  north: boolean,
): { lat: number; lon: number } {
  const epsg = north ? `EPSG:326${String(zone).padStart(2, '0')}` : `EPSG:327${String(zone).padStart(2, '0')}`
  const [lon, lat] = proj4(epsg, 'EPSG:4326', [easting, northing]) as [number, number]
  return { lat, lon }
}

function latLonToUtm(
  lat: number,
  lon: number,
  zone: number,
  north: boolean,
): { easting: number; northing: number } {
  const epsg = north ? `EPSG:326${String(zone).padStart(2, '0')}` : `EPSG:327${String(zone).padStart(2, '0')}`
  const [easting, northing] = proj4('EPSG:4326', epsg, [lon, lat]) as [number, number]
  return { easting, northing }
}

function matMulVec3(
  rot: [[number, number, number], [number, number, number], [number, number, number]],
  v: [number, number, number],
): [number, number, number] {
  return [
    rot[0][0] * v[0] + rot[0][1] * v[1] + rot[0][2] * v[2],
    rot[1][0] * v[0] + rot[1][1] * v[1] + rot[1][2] * v[2],
    rot[2][0] * v[0] + rot[2][1] * v[1] + rot[2][2] * v[2],
  ]
}

function matTranspose(
  rot: [[number, number, number], [number, number, number], [number, number, number]],
): [[number, number, number], [number, number, number], [number, number, number]] {
  return [
    [rot[0][0], rot[1][0], rot[2][0]],
    [rot[0][1], rot[1][1], rot[2][1]],
    [rot[0][2], rot[1][2], rot[2][2]],
  ]
}

/** Site centre in WGS-84, from the geo-transform's UTM origin.
 *
 * Used to open map panes over the reconstruction rather than a fixed default.
 */
export function geoOriginLatLon(
  geo: GeoTransform | null | undefined,
): { lat: number; lon: number } | null {
  if (!geo?.utm_zone || !geo.utm_origin) return null
  const parsed = parseUtmZone(geo.utm_zone)
  if (!parsed) return null
  return utmToLatLon(geo.utm_origin[0], geo.utm_origin[1], parsed.zone, parsed.north)
}

export function worldToGps(world: WorldPoint, geo: GeoTransform): GpsPoint | null {
  const parsed = parseUtmZone(geo.utm_zone)
  if (!parsed) return null

  const rot = geo.rotation
  const scaled = matMulVec3(rot, [world.x, world.y, world.z])
  const utmE = geo.scale * scaled[0] + geo.translation[0] + geo.utm_origin[0]
  const utmN = geo.scale * scaled[1] + geo.translation[1] + geo.utm_origin[1]
  const alt = geo.scale * scaled[2] + geo.translation[2]

  const { lat, lon } = utmToLatLon(utmE, utmN, parsed.zone, parsed.north)
  return { lat, lon, alt }
}

export function gpsToWorld(gps: GpsPoint, geo: GeoTransform): WorldPoint | null {
  const parsed = parseUtmZone(geo.utm_zone)
  if (!parsed) return null

  const { easting, northing } = latLonToUtm(gps.lat, gps.lon, parsed.zone, parsed.north)

  // Invert: P_world = R^T * ((P_utm - origin - translation) / scale)
  const utmX = (easting - geo.utm_origin[0] - geo.translation[0]) / geo.scale
  const utmY = (northing - geo.utm_origin[1] - geo.translation[1]) / geo.scale
  const utmZ = (gps.alt - geo.translation[2]) / geo.scale

  const rotT = matTranspose(geo.rotation)
  const [x, y, z] = matMulVec3(rotT, [utmX, utmY, utmZ])
  return { x, y, z }
}

// ---------------------------------------------------------------------------
// Ray-cast hook: canvas click → world position (THREE.Plane intersection)
// ---------------------------------------------------------------------------

export interface RayCastResult {
  worldPos: { x: number; y: number; z: number }
  screenPos: { x: number; y: number }
}

export function deriveGroundPlaneY(geo: GeoTransform | null | undefined): number {
  if (geo?.translation?.[2] == null) return 0
  return -geo.translation[2] / (geo.scale || 1)
}

export function useRayCast(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  viewerRef: RefObject<any>,
  containerRef: RefObject<HTMLDivElement | null>,
  groundY = 0,
) {
  // Memoized: consumers keep `castRay` in effect dep arrays, so a fresh
  // identity every render re-attached the canvas listeners on every render (#664).
  const castRay = useCallback(async (e: MouseEvent): Promise<RayCastResult | null> => {
    const viewer = viewerRef.current
    const container = containerRef.current
    if (!viewer || !container) return null

    const THREE = await import('three')
    const camera = viewer.camera
    if (!camera) return null

    const rect = container.getBoundingClientRect()
    const ndcX = ((e.clientX - rect.left) / rect.width) * 2 - 1
    const ndcY = -((e.clientY - rect.top) / rect.height) * 2 + 1

    const raycaster = new THREE.Raycaster()
    raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), camera)

    // Intersect with a ground plane derived from reconstruction metadata.
    // Falling back to 0 preserves the old behavior when no transform exists.
    const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -groundY)
    const target = new THREE.Vector3()
    const hit = raycaster.ray.intersectPlane(groundPlane, target)
    if (!hit) return null

    return {
      worldPos: { x: target.x, y: target.y, z: target.z },
      screenPos: { x: e.clientX - rect.left, y: e.clientY - rect.top },
    }
  }, [viewerRef, containerRef, groundY])

  return { castRay }
}
