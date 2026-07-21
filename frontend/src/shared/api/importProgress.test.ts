import { describe, expect, it } from 'vitest'
import { importProgressRefetchInterval } from './importProgress'

describe('importProgressRefetchInterval', () => {
  it('polls every second while the import is pending or running', () => {
    expect(importProgressRefetchInterval('pending')).toBe(1000)
    expect(importProgressRefetchInterval('running')).toBe(1000)
  })

  it('keeps polling before the first progress response arrives (F5 regression)', () => {
    expect(importProgressRefetchInterval(undefined)).toBe(1000)
  })

  it('stops polling on done, error, or unknown', () => {
    expect(importProgressRefetchInterval('done')).toBe(false)
    expect(importProgressRefetchInterval('error')).toBe(false)
    // 'unknown' = server lost in-memory progress after an API restart (#507); polling it
    // forever leaves the import modal spinning at 1 s indefinitely.
    expect(importProgressRefetchInterval('unknown')).toBe(false)
  })
})
