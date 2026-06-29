import { describe, it, expect } from 'vitest'
import { generatePoints } from './pointFieldData'

describe('generatePoints', () => {
  it('produces the requested count', () => {
    expect(generatePoints(120, 7)).toHaveLength(120)
  })

  it('is deterministic for a given seed', () => {
    expect(generatePoints(50, 42)).toEqual(generatePoints(50, 42))
  })

  it('varies with the seed', () => {
    expect(generatePoints(50, 1)).not.toEqual(generatePoints(50, 2))
  })

  it('keeps every point inside the 0..100 box with sane radius/opacity', () => {
    for (const p of generatePoints(200, 9)) {
      expect(p.x).toBeGreaterThanOrEqual(0)
      expect(p.x).toBeLessThanOrEqual(100)
      expect(p.y).toBeGreaterThanOrEqual(0)
      expect(p.y).toBeLessThanOrEqual(100)
      expect(p.r).toBeGreaterThan(0)
      expect(p.o).toBeGreaterThan(0)
      expect(p.o).toBeLessThanOrEqual(1)
      expect([0, 1, 2]).toContain(p.c)
    }
  })
})
