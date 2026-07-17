export function formatTrendValue(value: number | null, digits = 1): string {
  return value === null ? '—' : value.toFixed(digits)
}

export function formatTrendPercent(value: number | null): string {
  return value === null ? '—' : `${formatTrendValue(value)}%`
}

export function formatTrendDate(value: string | null): string {
  if (!value) return 'Unknown date'
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
