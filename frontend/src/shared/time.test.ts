import { describe, expect, it } from 'vitest'
import { formatEta, formatRemainingDuration } from './time'

describe('formatRemainingDuration', () => {
  it('formats seconds, minutes, and hours as approximate remaining time', () => {
    expect(formatRemainingDuration(42)).toBe('~42s remaining')
    expect(formatRemainingDuration(90)).toBe('~2 min remaining')
    expect(formatRemainingDuration(7_200)).toBe('~2h remaining')
    expect(formatRemainingDuration(7_500)).toBe('~2h 5m remaining')
  })
})

describe('formatEta', () => {
  it('estimates remaining time from elapsed time and percent complete', () => {
    const startedAt = '2026-06-23T12:00:00.000Z'
    const nowMs = new Date('2026-06-23T12:10:00.000Z').getTime()

    expect(formatEta(startedAt, 25, nowMs)).toBe('~30 min remaining')
    expect(formatEta(startedAt, 50, nowMs)).toBe('~10 min remaining')
  })

  it('returns null until the estimate has enough valid data', () => {
    const nowMs = new Date('2026-06-23T12:10:00.000Z').getTime()

    expect(formatEta(null, 50, nowMs)).toBeNull()
    expect(formatEta('not-a-date', 50, nowMs)).toBeNull()
    expect(formatEta('2026-06-23T12:00:00.000Z', 0, nowMs)).toBeNull()
    expect(formatEta('2026-06-23T12:00:00.000Z', 100, nowMs)).toBeNull()
  })
})
