import { describe, expect, it } from 'vitest'
import { isGpsWarning, prioritizeWarnings } from './warningPriority'

describe('isGpsWarning', () => {
  it('flags warnings mentioning GPS', () => {
    expect(isGpsWarning('GPS coordinates are frozen across 12 consecutive points')).toBe(true)
  })

  it('is case-insensitive', () => {
    expect(isGpsWarning('gps points sit at (0, 0); the receiver likely had no fix')).toBe(true)
  })

  it('does not flag unrelated warnings', () => {
    expect(isGpsWarning('Many frames are below the blur threshold')).toBe(false)
  })
})

describe('prioritizeWarnings', () => {
  it('surfaces GPS-lock warnings ahead of other warnings', () => {
    const warnings = [
      'Many frames are below the blur threshold',
      'GPS coordinates are frozen across 12 consecutive points',
      'Timestamp gaps found; verify continuous coverage across the flight',
    ]
    expect(prioritizeWarnings(warnings, 2)).toEqual([
      'GPS coordinates are frozen across 12 consecutive points',
      'Many frames are below the blur threshold',
    ])
  })

  it('preserves relative order within each priority group', () => {
    const warnings = [
      'Exposure issues detected in a significant share of frames',
      '2 implausible position jump(s) between consecutive GPS points',
      '3 of 40 GPS points sit at (0, 0); the receiver likely had no satellite fix',
    ]
    expect(prioritizeWarnings(warnings, 10)).toEqual([
      '2 implausible position jump(s) between consecutive GPS points',
      '3 of 40 GPS points sit at (0, 0); the receiver likely had no satellite fix',
      'Exposure issues detected in a significant share of frames',
    ])
  })

  it('truncates to maxCount', () => {
    const warnings = ['a', 'b', 'c', 'd']
    expect(prioritizeWarnings(warnings, 2)).toEqual(['a', 'b'])
  })

  it('returns an empty array for no warnings', () => {
    expect(prioritizeWarnings([], 5)).toEqual([])
  })
})
