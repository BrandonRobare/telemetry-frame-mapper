// ---------------------------------------------------------------------------
// Weather / wind go-no-go advisor — pure evaluation + a thin Open-Meteo client.
//
// Open-Meteo (https://open-meteo.com) is a free, no-API-key forecast API, so
// this fetches directly from the browser rather than proxying through the
// backend — mirrors how PlanMap already talks to the OpenStreetMap tile CDN
// directly (frontend/src/features/plan/PlanMap.tsx). The backend has no
// existing pattern for calling outbound third-party HTTP APIs (terrain.py's
// TerrainService reads a local GeoTIFF, it doesn't fetch anything), so there
// is no backend convention to follow here.
//
// evaluateFlightWeather() is the pure decision core: given a handful of
// forecast samples (current hour + next few hours) it returns a go / caution
// / no-go verdict plus the specific factors that drove it. Network access and
// GeoJSON parsing are kept in separate, independently testable functions so
// the verdict logic itself has zero I/O.
// ---------------------------------------------------------------------------

export interface WeatherPoint {
  /** ISO-ish timestamp as returned by Open-Meteo (local time, "auto" timezone). */
  timeIso: string
  windMph: number
  gustMph: number
  precipProbPct: number
  tempF: number
}

export type WeatherVerdict = 'go' | 'caution' | 'no-go'

export interface WeatherFactor {
  label: string
  verdict: WeatherVerdict
  detail: string
}

export interface WeatherAssessment {
  verdict: WeatherVerdict
  factors: WeatherFactor[]
  summary: string
}

export interface WeatherThresholds {
  windCautionMph: number
  windNoGoMph: number
  gustCautionMph: number
  gustNoGoMph: number
  precipCautionPct: number
  precipNoGoPct: number
  tempMinCautionF: number
  tempMinNoGoF: number
  tempMaxCautionF: number
  tempMaxNoGoF: number
}

/**
 * Typical small-drone (DJI Mini/Air-class) field-ops limits. Sustained wind
 * and gust figures track common hobbyist/commercial small-UAS guidance
 * (~15 mph sustained / ~20 mph gust caution, ~20-25 mph hard limits for
 * sub-250g-to-Mavic-class airframes). Not a certified flight-safety source —
 * treat as a conservative default, not a legal limit.
 */
export const DEFAULT_WEATHER_THRESHOLDS: WeatherThresholds = {
  windCautionMph: 15,
  windNoGoMph: 20,
  gustCautionMph: 20,
  gustNoGoMph: 25,
  precipCautionPct: 30,
  precipNoGoPct: 70,
  tempMinCautionF: 40,
  tempMinNoGoF: 32,
  tempMaxCautionF: 95,
  tempMaxNoGoF: 104,
}

type Severity = 0 | 1 | 2 // go / caution / no-go

const SEVERITY_TO_VERDICT: Record<Severity, WeatherVerdict> = {
  0: 'go',
  1: 'caution',
  2: 'no-go',
}

interface WorstSample {
  severity: Severity
  point: WeatherPoint
}

function worstOf(points: WeatherPoint[], severityFn: (p: WeatherPoint) => Severity): WorstSample {
  let worst: WorstSample = { severity: 0, point: points[0] }
  for (const point of points) {
    const severity = severityFn(point)
    if (severity > worst.severity) worst = { severity, point }
  }
  return worst
}

function formatTime(timeIso: string): string {
  // Open-Meteo "auto" timezone times look like "2026-07-11T17:00" — just
  // surface the time-of-day portion, no timezone math needed for display.
  const match = /T(\d{2}:\d{2})/.exec(timeIso)
  return match ? match[1] : timeIso
}

/**
 * Pure verdict logic: no network, no clock reads. Given a set of forecast
 * samples (current + near-term hours), returns the worst-case go/caution/
 * no-go verdict across the window plus the specific factors that drove it.
 */
export function evaluateFlightWeather(
  points: WeatherPoint[],
  thresholds: WeatherThresholds = DEFAULT_WEATHER_THRESHOLDS,
): WeatherAssessment {
  if (points.length === 0) {
    return {
      verdict: 'caution',
      factors: [],
      summary: 'No forecast data available — treat conditions as unverified.',
    }
  }

  const wind = worstOf(points, (p) => {
    if (p.windMph >= thresholds.windNoGoMph) return 2
    if (p.windMph >= thresholds.windCautionMph) return 1
    return 0
  })
  const gust = worstOf(points, (p) => {
    if (p.gustMph >= thresholds.gustNoGoMph) return 2
    if (p.gustMph >= thresholds.gustCautionMph) return 1
    return 0
  })
  const precip = worstOf(points, (p) => {
    if (p.precipProbPct >= thresholds.precipNoGoPct) return 2
    if (p.precipProbPct >= thresholds.precipCautionPct) return 1
    return 0
  })
  const coldTemp = worstOf(points, (p) => {
    if (p.tempF <= thresholds.tempMinNoGoF) return 2
    if (p.tempF <= thresholds.tempMinCautionF) return 1
    return 0
  })
  const hotTemp = worstOf(points, (p) => {
    if (p.tempF >= thresholds.tempMaxNoGoF) return 2
    if (p.tempF >= thresholds.tempMaxCautionF) return 1
    return 0
  })

  const factors: WeatherFactor[] = []
  if (wind.severity > 0) {
    factors.push({
      label: 'Sustained wind',
      verdict: SEVERITY_TO_VERDICT[wind.severity],
      detail: `${wind.point.windMph.toFixed(0)} mph at ${formatTime(wind.point.timeIso)}`,
    })
  }
  if (gust.severity > 0) {
    factors.push({
      label: 'Wind gusts',
      verdict: SEVERITY_TO_VERDICT[gust.severity],
      detail: `${gust.point.gustMph.toFixed(0)} mph at ${formatTime(gust.point.timeIso)}`,
    })
  }
  if (precip.severity > 0) {
    factors.push({
      label: 'Precipitation',
      verdict: SEVERITY_TO_VERDICT[precip.severity],
      detail: `${precip.point.precipProbPct.toFixed(0)}% chance at ${formatTime(precip.point.timeIso)}`,
    })
  }
  if (coldTemp.severity > 0) {
    factors.push({
      label: 'Low temperature',
      verdict: SEVERITY_TO_VERDICT[coldTemp.severity],
      detail: `${coldTemp.point.tempF.toFixed(0)}°F at ${formatTime(coldTemp.point.timeIso)}`,
    })
  }
  if (hotTemp.severity > 0) {
    factors.push({
      label: 'High temperature',
      verdict: SEVERITY_TO_VERDICT[hotTemp.severity],
      detail: `${hotTemp.point.tempF.toFixed(0)}°F at ${formatTime(hotTemp.point.timeIso)}`,
    })
  }

  const overallSeverity = Math.max(
    wind.severity,
    gust.severity,
    precip.severity,
    coldTemp.severity,
    hotTemp.severity,
  ) as Severity
  const verdict = SEVERITY_TO_VERDICT[overallSeverity]

  const summary =
    verdict === 'go'
      ? 'Conditions look good for flight.'
      : verdict === 'caution'
        ? 'Marginal conditions — review the factors below before flying.'
        : 'Conditions exceed safe small-drone limits — do not fly.'

  return { verdict, factors, summary }
}

// ---------------------------------------------------------------------------
// Open-Meteo client
// ---------------------------------------------------------------------------

export interface OpenMeteoResponse {
  hourly?: {
    time: string[]
    wind_speed_10m?: number[]
    wind_gusts_10m?: number[]
    precipitation_probability?: number[]
    temperature_2m?: number[]
  }
}

/** Pure mapper from the raw Open-Meteo response shape into WeatherPoint[]. */
export function parseOpenMeteoForecast(raw: OpenMeteoResponse): WeatherPoint[] {
  const hourly = raw.hourly
  if (!hourly || !Array.isArray(hourly.time)) return []
  return hourly.time.map((timeIso, i) => ({
    timeIso,
    windMph: hourly.wind_speed_10m?.[i] ?? 0,
    gustMph: hourly.wind_gusts_10m?.[i] ?? 0,
    precipProbPct: hourly.precipitation_probability?.[i] ?? 0,
    tempF: hourly.temperature_2m?.[i] ?? 0,
  }))
}

const OPEN_METEO_URL = 'https://api.open-meteo.com/v1/forecast'

/** Current hour + this many near-term hours of hourly forecast. */
const FORECAST_HOURS = 6

/**
 * Fetches current + near-term hourly forecast for a coordinate from
 * Open-Meteo (no API key required). Pass a custom `fetchImpl` in tests to
 * avoid real network calls.
 */
export async function fetchWeatherForecast(
  lat: number,
  lon: number,
  fetchImpl: typeof fetch = fetch,
): Promise<WeatherPoint[]> {
  const params = new URLSearchParams({
    latitude: String(lat),
    longitude: String(lon),
    hourly: 'wind_speed_10m,wind_gusts_10m,precipitation_probability,temperature_2m',
    wind_speed_unit: 'mph',
    temperature_unit: 'fahrenheit',
    forecast_hours: String(FORECAST_HOURS),
    timezone: 'auto',
  })

  const res = await fetchImpl(`${OPEN_METEO_URL}?${params.toString()}`)
  if (!res.ok) {
    throw new Error(`Weather request failed: ${res.status}`)
  }
  const raw = (await res.json()) as OpenMeteoResponse
  return parseOpenMeteoForecast(raw)
}

// ---------------------------------------------------------------------------
// GeoJSON centroid — enough to turn a drawn target-area polygon into a
// lat/lon for the weather lookup. Not a precision geometric centroid (it
// simple-averages ring vertices, including the repeated closing vertex);
// good enough for picking a forecast grid cell.
// ---------------------------------------------------------------------------

export interface LatLon {
  lat: number
  lon: number
}

interface PolygonGeometry {
  type: 'Polygon'
  coordinates: number[][][]
}

interface MultiPolygonGeometry {
  type: 'MultiPolygon'
  coordinates: number[][][][]
}

export type CentroidGeometry =
  | PolygonGeometry
  | MultiPolygonGeometry
  | { type: string; coordinates: unknown }

export function computeCentroid(geometry: CentroidGeometry | null | undefined): LatLon | null {
  if (!geometry) return null

  let ring: number[][] | undefined
  if (geometry.type === 'Polygon') {
    ring = (geometry as PolygonGeometry).coordinates[0]
  } else if (geometry.type === 'MultiPolygon') {
    ring = (geometry as MultiPolygonGeometry).coordinates[0]?.[0]
  }
  if (!ring || ring.length === 0) return null

  let sumLat = 0
  let sumLon = 0
  let count = 0
  for (const vertex of ring) {
    const [lon, lat] = vertex
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue
    sumLon += lon
    sumLat += lat
    count += 1
  }
  if (count === 0) return null

  return { lat: sumLat / count, lon: sumLon / count }
}
