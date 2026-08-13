export interface RenderableGeoJSON {
  type: string
  coordinates?: unknown
  geometry?: unknown
  geometries?: unknown
  features?: unknown
  properties?: unknown
}

function isPosition(value: unknown): value is number[] {
  return Array.isArray(value) && value.length >= 2 && value.every(Number.isFinite)
}

function isPositionArray(value: unknown): boolean {
  return Array.isArray(value) && value.length > 0 && value.every(isPosition)
}

function isNestedPositionArray(value: unknown): boolean {
  return Array.isArray(value) && value.length > 0 && value.every(isPositionArray)
}

export function isRenderableGeoJSON(value: unknown): value is RenderableGeoJSON {
  if (!value || typeof value !== 'object') return false
  const geojson = value as RenderableGeoJSON

  switch (geojson.type) {
    case 'Point':
      return isPosition(geojson.coordinates)
    case 'MultiPoint':
    case 'LineString':
      return isPositionArray(geojson.coordinates)
    case 'MultiLineString':
    case 'Polygon':
      return isNestedPositionArray(geojson.coordinates)
    case 'MultiPolygon':
      return Array.isArray(geojson.coordinates)
        && geojson.coordinates.length > 0
        && geojson.coordinates.every(isNestedPositionArray)
    case 'GeometryCollection':
      return Array.isArray(geojson.geometries) && geojson.geometries.every(isRenderableGeoJSON)
    case 'Feature':
      return isRenderableGeoJSON(geojson.geometry)
    case 'FeatureCollection':
      return Array.isArray(geojson.features) && geojson.features.every(isRenderableGeoJSON)
    default:
      return false
  }
}

export function parseRenderableGeoJSON(value: string | null | undefined): RenderableGeoJSON | null {
  if (!value) return null
  try {
    const parsed: unknown = JSON.parse(value)
    return isRenderableGeoJSON(parsed) ? parsed : null
  } catch {
    return null
  }
}
