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

export function useRayCast(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  viewerRef: RefObject<any>,
  containerRef: RefObject<HTMLDivElement | null>,
) {
  async function castRay(e: MouseEvent): Promise<RayCastResult | null> {
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

    // Intersect with a ground plane at Y = estimated scene median
    // Default Y = 0 works for most COLMAP reconstructions where
    // the ground is near the world origin.
    const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)
    const target = new THREE.Vector3()
    const hit = raycaster.ray.intersectPlane(groundPlane, target)
    if (!hit) return null

    return {
      worldPos: { x: target.x, y: target.y, z: target.z },
      screenPos: { x: e.clientX - rect.left, y: e.clientY - rect.top },
    }
  }

  return { castRay }
}
