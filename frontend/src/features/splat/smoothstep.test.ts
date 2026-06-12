import { describe, expect, it } from 'vitest'
import { smoothstep } from './smoothstep'

describe('smoothstep', () => {
  it('is exact at the endpoints and midpoint', () => {
    expect(smoothstep(0)).toBe(0)
    expect(smoothstep(1)).toBe(1)
    expect(smoothstep(0.5)).toBe(0.5)
  })

  it('matches t*t*(3-2t) — the server-side trainer formula — at sample points', () => {
    for (const t of [0.1, 0.25, 0.6, 0.9]) {
      expect(smoothstep(t)).toBeCloseTo(t * t * (3 - 2 * t), 12)
    }
  })

  it('eases in and out (slower than linear near 0, faster near 1)', () => {
    expect(smoothstep(0.1)).toBeLessThan(0.1)
    expect(smoothstep(0.9)).toBeGreaterThan(0.9)
  })
})
