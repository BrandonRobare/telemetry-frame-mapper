import { useQuery } from '@tanstack/react-query'
import { evaluateFlightWeather, fetchWeatherForecast, type WeatherVerdict } from './weatherAdvisor'

interface Props {
  /** Centroid of the drawn target area, or null before one has been drawn. */
  lat: number | null
  lon: number | null
}

const VERDICT_COLOR: Record<WeatherVerdict, string> = {
  go: 'var(--success, #16a34a)',
  caution: 'var(--warning, #d97706)',
  'no-go': 'var(--error, #dc2626)',
}

const VERDICT_LABEL: Record<WeatherVerdict, string> = {
  go: 'GO',
  caution: 'CAUTION',
  'no-go': 'NO-GO',
}

export default function WeatherAdvisorPanel({ lat, lon }: Props) {
  const hasCoords = lat != null && lon != null

  const { data, isLoading, isError } = useQuery({
    queryKey: ['weather-advisor', lat, lon],
    queryFn: () => fetchWeatherForecast(lat as number, lon as number),
    enabled: hasCoords,
    staleTime: 10 * 60_000, // forecasts don't change minute to minute
    retry: 1,
  })

  const assessment = data ? evaluateFlightWeather(data) : null

  return (
    <div style={{ marginTop: 20 }}>
      <h3
        className="text-xs font-semibold uppercase"
        style={{ color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 12 }}
      >
        Weather Advisor
      </h3>

      <div
        style={{
          padding: '10px 12px',
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
        }}
      >
        {!hasCoords && (
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
            Draw a target area to check conditions.
          </div>
        )}

        {hasCoords && isLoading && (
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
            Checking forecast…
          </div>
        )}

        {hasCoords && isError && (
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
            Weather unavailable — check your connection.
          </div>
        )}

        {hasCoords && assessment && (
          <>
            <div className="flex justify-between items-center" style={{ marginBottom: 8 }}>
              <span
                className="text-xs font-semibold"
                style={{ color: VERDICT_COLOR[assessment.verdict], letterSpacing: '0.04em' }}
              >
                {VERDICT_LABEL[assessment.verdict]}
              </span>
            </div>
            <div
              className="text-xs"
              style={{
                color: 'var(--text-muted)',
                marginBottom: assessment.factors.length > 0 ? 8 : 0,
              }}
            >
              {assessment.summary}
            </div>
            {assessment.factors.map((factor) => (
              <div
                key={factor.label}
                className="flex justify-between text-xs"
                style={{ marginBottom: 4 }}
              >
                <span style={{ color: 'var(--text-muted)' }}>{factor.label}</span>
                <span
                  style={{
                    color: VERDICT_COLOR[factor.verdict],
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {factor.detail}
                </span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
