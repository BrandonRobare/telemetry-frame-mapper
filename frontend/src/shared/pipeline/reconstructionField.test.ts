import { describe, it, expect } from 'vitest'
import { generateReconstructionField, heightAt, FIELD_RADIUS } from './reconstructionField'

describe('generateReconstructionField', () => {
  it('produces count*3 position buffers and count tints', () => {
    const f = generateReconstructionField(100, 7)
    expect(f.scatter).toHaveLength(300)
    expect(f.target).toHaveLength(300)
    expect(f.tint).toHaveLength(100)
  })

  it('is deterministic for a given seed', () => {
    const a = generateReconstructionField(64, 3)
    const b = generateReconstructionField(64, 3)
    expect(Array.from(a.scatter)).toEqual(Array.from(b.scatter))
    expect(Array.from(a.target)).toEqual(Array.from(b.target))
  })

  it('varies with the seed', () => {
    const a = generateReconstructionField(64, 1)
    const b = generateReconstructionField(64, 2)
    expect(Array.from(a.scatter)).not.toEqual(Array.from(b.scatter))
  })

  it('keeps target points within the terrain disc and height range', () => {
    const f = generateReconstructionField(300, 9)
    for (let i = 0; i < 300; i++) {
      const x = f.target[i * 3]
      const y = f.target[i * 3 + 1]
      const z = f.target[i * 3 + 2]
      expect(Math.hypot(x, z)).toBeLessThanOrEqual(FIELD_RADIUS + 1e-6)
      expect(y).toBeGreaterThan(-0.2)
      expect(y).toBeLessThan(0.7)
      expect(Number.isFinite(y)).toBe(true)
    }
  })

  it('heightAt is finite and bounded', () => {
    for (let i = 0; i <= 50; i++) {
      const x = (i / 50) * 2 - 1
      const hh = heightAt(x, -x)
      expect(Number.isFinite(hh)).toBe(true)
      expect(hh).toBeGreaterThan(-0.3)
      expect(hh).toBeLessThan(0.7)
    }
    expect(heightAt(0.15, -0.1)).toBeGreaterThan(0.35)
    expect(heightAt(0.15, -0.1)).toBeLessThan(0.7)
  })

  it('tint values are in 0..1', () => {
    const f = generateReconstructionField(120, 5)
    for (const t of f.tint) {
      expect(t).toBeGreaterThanOrEqual(0)
      expect(t).toBeLessThanOrEqual(1)
    }
  })
})
