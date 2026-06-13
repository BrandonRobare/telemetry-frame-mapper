import { describe, expect, it } from 'vitest'
import { formatLogTimestamp } from './formatLogTimestamp'

describe('formatLogTimestamp', () => {
  it('renders an em dash for a null timestamp', () => {
    expect(formatLogTimestamp(null)).toBe('—')
  })

  it('never renders "Invalid Date" for unparseable input (F6 regression)', () => {
    expect(formatLogTimestamp('not-a-date')).toBe('—')
  })

  it('formats a valid ISO timestamp with toLocaleString', () => {
    const iso = '2026-06-11T14:30:00Z'
    const result = formatLogTimestamp(iso)
    expect(result).not.toContain('Invalid')
    expect(result).toBe(new Date(iso).toLocaleString())
  })
})
