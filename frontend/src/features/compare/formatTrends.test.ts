import { describe, expect, it } from 'vitest'
import { formatTrendDate, formatTrendPercent, formatTrendValue } from './formatTrends'

describe('trend formatters', () => {
  it('shows missing persisted metrics as an em dash', () => {
    expect(formatTrendValue(null)).toBe('—')
    expect(formatTrendPercent(null)).toBe('—')
  })

  it('formats numeric metrics without inventing values', () => {
    expect(formatTrendValue(42.345)).toBe('42.3')
    expect(formatTrendPercent(87.5)).toBe('87.5%')
  })

  it('labels missing session dates explicitly', () => {
    expect(formatTrendDate(null)).toBe('Unknown date')
  })
})
