import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  DEFAULT_WEATHER_THRESHOLDS,
  computeCentroid,
  evaluateFlightWeather,
  parseOpenMeteoForecast,
  fetchWeatherForecast,
  type OpenMeteoResponse,
  type WeatherPoint,
} from './weatherAdvisor'

describe('computeCentroid', () => {
  it('averages the exterior ring of a Polygon (GeoJSON [lon, lat] order)', () => {
    const geometry = {
      type: 'Polygon' as const,
      coordinates: [
        [
          [-100, 40],
          [-100, 42],
          [-98, 42],
          [-98, 40],
          [-100, 40], // closed ring — first point repeated
        ],
      ],
    }
    const centroid = computeCentroid(geometry)
    expect(centroid).not.toBeNull()
    // Simple average of ring points (including the repeated closing vertex) — close enough
    // for a weather lookup, not a precision geometric centroid.
    expect(centroid!.lat).toBeCloseTo(40.8, 5)
    expect(centroid!.lon).toBeCloseTo(-99.2, 5)
  })

  it('uses the outer ring of a MultiPolygon', () => {
    const geometry = {
      type: 'MultiPolygon' as const,
      coordinates: [
        [
          [
            [10, 10],
            [10, 20],
            [20, 20],
            [20, 10],
            [10, 10],
          ],
        ],
      ],
    }
    const centroid = computeCentroid(geometry)
    expect(centroid).not.toBeNull()
    // Simple average including the repeated closing vertex: (10+10+20+20+10)/5 = 14
    expect(centroid!.lat).toBeCloseTo(14, 5)
    expect(centroid!.lon).toBeCloseTo(14, 5)
  })

  it('returns null for null/undefined geometry', () => {
    expect(computeCentroid(null)).toBeNull()
    expect(computeCentroid(undefined)).toBeNull()
  })

  it('returns null for unsupported geometry types', () => {
    expect(computeCentroid({ type: 'Point', coordinates: [1, 2] } as never)).toBeNull()
  })

  it('returns null for an empty ring', () => {
    expect(computeCentroid({ type: 'Polygon', coordinates: [[]] })).toBeNull()
  })
})

describe('parseOpenMeteoForecast', () => {
  it('maps hourly arrays into WeatherPoint entries', () => {
    const raw: OpenMeteoResponse = {
      hourly: {
        time: ['2026-07-11T14:00', '2026-07-11T15:00'],
        wind_speed_10m: [8, 22],
        wind_gusts_10m: [12, 30],
        precipitation_probability: [5, 60],
        temperature_2m: [75, 78],
      },
    }
    const points = parseOpenMeteoForecast(raw)
    expect(points).toHaveLength(2)
    expect(points[0]).toEqual({
      timeIso: '2026-07-11T14:00',
      windMph: 8,
      gustMph: 12,
      precipProbPct: 5,
      tempF: 75,
    })
    expect(points[1].windMph).toBe(22)
  })

  it('returns an empty array when hourly data is missing', () => {
    expect(parseOpenMeteoForecast({})).toEqual([])
  })

  it('defaults missing metric arrays to 0 rather than throwing', () => {
    const raw: OpenMeteoResponse = { hourly: { time: ['2026-07-11T14:00'] } }
    const points = parseOpenMeteoForecast(raw)
    expect(points).toEqual([
      { timeIso: '2026-07-11T14:00', windMph: 0, gustMph: 0, precipProbPct: 0, tempF: 0 },
    ])
  })
})

const calmPoint: WeatherPoint = {
  timeIso: '2026-07-11T14:00',
  windMph: 5,
  gustMph: 8,
  precipProbPct: 5,
  tempF: 70,
}

describe('evaluateFlightWeather', () => {
  it('returns "go" with no factors when every sample is comfortably within limits', () => {
    const result = evaluateFlightWeather([calmPoint, { ...calmPoint, timeIso: '2026-07-11T15:00' }])
    expect(result.verdict).toBe('go')
    expect(result.factors).toEqual([])
  })

  it('flags "caution" for sustained wind between the caution and no-go thresholds', () => {
    const point = { ...calmPoint, windMph: 17 }
    const result = evaluateFlightWeather([point])
    expect(result.verdict).toBe('caution')
    expect(result.factors).toHaveLength(1)
    expect(result.factors[0].label).toBe('Sustained wind')
    expect(result.factors[0].verdict).toBe('caution')
  })

  it('flags "no-go" for sustained wind at/above the no-go threshold', () => {
    const point = { ...calmPoint, windMph: 25 }
    const result = evaluateFlightWeather([point])
    expect(result.verdict).toBe('no-go')
    expect(result.factors[0].verdict).toBe('no-go')
  })

  it('flags gusts independently of sustained wind', () => {
    const point = { ...calmPoint, gustMph: 27 }
    const result = evaluateFlightWeather([point])
    expect(result.verdict).toBe('no-go')
    expect(result.factors.some((f) => f.label === 'Wind gusts' && f.verdict === 'no-go')).toBe(
      true,
    )
  })

  it('flags high precipitation probability', () => {
    const cautionResult = evaluateFlightWeather([{ ...calmPoint, precipProbPct: 45 }])
    expect(cautionResult.verdict).toBe('caution')
    expect(cautionResult.factors[0].label).toBe('Precipitation')

    const noGoResult = evaluateFlightWeather([{ ...calmPoint, precipProbPct: 85 }])
    expect(noGoResult.verdict).toBe('no-go')
  })

  it('flags cold temperatures', () => {
    const cautionResult = evaluateFlightWeather([{ ...calmPoint, tempF: 38 }])
    expect(cautionResult.verdict).toBe('caution')
    expect(cautionResult.factors[0].label).toBe('Low temperature')

    const noGoResult = evaluateFlightWeather([{ ...calmPoint, tempF: 20 }])
    expect(noGoResult.verdict).toBe('no-go')
  })

  it('flags hot temperatures', () => {
    const cautionResult = evaluateFlightWeather([{ ...calmPoint, tempF: 98 }])
    expect(cautionResult.verdict).toBe('caution')
    expect(cautionResult.factors[0].label).toBe('High temperature')

    const noGoResult = evaluateFlightWeather([{ ...calmPoint, tempF: 108 }])
    expect(noGoResult.verdict).toBe('no-go')
  })

  it('takes the worst case across multiple near-term samples, not just the first', () => {
    const points = [calmPoint, { ...calmPoint, timeIso: '2026-07-11T17:00', windMph: 26 }]
    const result = evaluateFlightWeather(points)
    expect(result.verdict).toBe('no-go')
    expect(result.factors[0].detail).toContain('17:00')
  })

  it('reports every triggered factor when several thresholds are crossed at once', () => {
    const point = { ...calmPoint, windMph: 18, precipProbPct: 40 }
    const result = evaluateFlightWeather([point])
    expect(result.verdict).toBe('caution')
    const labels = result.factors.map((f) => f.label).sort()
    expect(labels).toEqual(['Precipitation', 'Sustained wind'])
  })

  it('returns "caution" with an empty-data summary and no factors for an empty sample set', () => {
    const result = evaluateFlightWeather([])
    expect(result.verdict).toBe('caution')
    expect(result.factors).toEqual([])
    expect(result.summary.toLowerCase()).toContain('no forecast data')
  })

  it('honors custom thresholds', () => {
    const strict = { ...DEFAULT_WEATHER_THRESHOLDS, windCautionMph: 3, windNoGoMph: 6 }
    const result = evaluateFlightWeather([{ ...calmPoint, windMph: 5 }], strict)
    expect(result.verdict).toBe('caution')
  })
})

describe('fetchWeatherForecast', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('requests hourly wind/gust/precip/temp fields in mph + fahrenheit for the given coordinates', async () => {
    const raw: OpenMeteoResponse = {
      hourly: {
        time: ['2026-07-11T14:00'],
        wind_speed_10m: [9],
        wind_gusts_10m: [14],
        precipitation_probability: [10],
        temperature_2m: [72],
      },
    }
    let capturedUrl = ''
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      capturedUrl = String(input)
      return new Response(JSON.stringify(raw), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    })

    const points = await fetchWeatherForecast(40.5, -99.2, fetchImpl as unknown as typeof fetch)

    expect(points).toHaveLength(1)
    expect(points[0].windMph).toBe(9)

    const calledUrl = new URL(capturedUrl)
    expect(calledUrl.origin + calledUrl.pathname).toBe('https://api.open-meteo.com/v1/forecast')
    expect(calledUrl.searchParams.get('latitude')).toBe('40.5')
    expect(calledUrl.searchParams.get('longitude')).toBe('-99.2')
    expect(calledUrl.searchParams.get('wind_speed_unit')).toBe('mph')
    expect(calledUrl.searchParams.get('temperature_unit')).toBe('fahrenheit')
    expect(calledUrl.searchParams.get('hourly')).toContain('wind_speed_10m')
  })

  it('throws when the API responds with a non-ok status', async () => {
    const fetchImpl = vi.fn(async () => new Response('', { status: 503 }))
    await expect(
      fetchWeatherForecast(40.5, -99.2, fetchImpl as unknown as typeof fetch),
    ).rejects.toThrow()
  })

  it('propagates network failures (e.g. offline) so callers can show an unavailable state', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    })
    await expect(
      fetchWeatherForecast(40.5, -99.2, fetchImpl as unknown as typeof fetch),
    ).rejects.toThrow('Failed to fetch')
  })
})
