import { describe, expect, it } from 'vitest'
import { formatDurationS, parseFlightEntryForm } from './flightEntries'

describe('formatDurationS', () => {
  it('formats null/undefined as an em dash', () => {
    expect(formatDurationS(null)).toBe('—')
    expect(formatDurationS(undefined)).toBe('—')
  })

  it('formats sub-minute durations as seconds', () => {
    expect(formatDurationS(42)).toBe('42s')
  })

  it('formats whole minutes', () => {
    expect(formatDurationS(600)).toBe('10m')
  })

  it('formats minutes and seconds', () => {
    expect(formatDurationS(750)).toBe('12m 30s')
  })

  it('rounds fractional seconds', () => {
    expect(formatDurationS(89.6)).toBe('1m 30s')
  })

  it('formats zero as 0s', () => {
    expect(formatDurationS(0)).toBe('0s')
  })
})

describe('parseFlightEntryForm', () => {
  it('builds a payload from filled fields (duration minutes -> seconds)', () => {
    const result = parseFlightEntryForm({
      batteryId: ' B-03 ',
      startPct: '98',
      endPct: '34',
      durationMin: '18',
      notes: ' windy ',
    })
    expect(result).toEqual({
      ok: true,
      payload: {
        battery_id: 'B-03',
        start_pct: 98,
        end_pct: 34,
        duration_s: 1080,
        notes: 'windy',
      },
    })
  })

  it('omits empty optional fields as null', () => {
    const result = parseFlightEntryForm({
      batteryId: 'B-01',
      startPct: '',
      endPct: '',
      durationMin: '',
      notes: '',
    })
    expect(result).toEqual({
      ok: true,
      payload: {
        battery_id: 'B-01',
        start_pct: null,
        end_pct: null,
        duration_s: null,
        notes: null,
      },
    })
  })

  it('requires a battery id', () => {
    const result = parseFlightEntryForm({
      batteryId: '   ',
      startPct: '',
      endPct: '',
      durationMin: '',
      notes: '',
    })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toMatch(/battery/i)
  })

  it('rejects percentages outside 0-100', () => {
    for (const [startPct, endPct] of [
      ['120', ''],
      ['', '-5'],
    ] as const) {
      const result = parseFlightEntryForm({
        batteryId: 'B-01',
        startPct,
        endPct,
        durationMin: '',
        notes: '',
      })
      expect(result.ok).toBe(false)
      if (!result.ok) expect(result.error).toMatch(/0.*100/)
    }
  })

  it('rejects non-numeric percentages and durations', () => {
    const bad = parseFlightEntryForm({
      batteryId: 'B-01',
      startPct: 'abc',
      endPct: '',
      durationMin: '',
      notes: '',
    })
    expect(bad.ok).toBe(false)

    const badDuration = parseFlightEntryForm({
      batteryId: 'B-01',
      startPct: '',
      endPct: '',
      durationMin: 'later',
      notes: '',
    })
    expect(badDuration.ok).toBe(false)
  })

  it('rejects negative durations', () => {
    const result = parseFlightEntryForm({
      batteryId: 'B-01',
      startPct: '',
      endPct: '',
      durationMin: '-3',
      notes: '',
    })
    expect(result.ok).toBe(false)
  })
})
