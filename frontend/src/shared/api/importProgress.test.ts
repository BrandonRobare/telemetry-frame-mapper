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

  it('stops polling only on done or error', () => {
    expect(importProgressRefetchInterval('done')).toBe(false)
    expect(importProgressRefetchInterval('error')).toBe(false)
  })
})
