import { describe, it, expect } from 'vitest'
import { deriveLogoMotion, logoRampColor } from './stages'
import type { StageKey, StageState } from './stages'

function states(map: Partial<Record<StageKey, StageState>>): Record<StageKey, StageState> {
  return {
    import: 'pending',
    review: 'pending',
    align: 'pending',
    train: 'pending',
    view: 'pending',
    export: 'pending',
    ...map,
  }
}

describe('deriveLogoMotion', () => {
  it('all pending → low organization, no active stage', () => {
    const m = deriveLogoMotion(states({}))
    expect(m.organization).toBeCloseTo(0.04)
    expect(m.solid).toBe(0)
    expect(m.activeIndex).toBe(-1)
    expect(m.failed).toBe(false)
  })

  it('reports the first active stage index', () => {
    const m = deriveLogoMotion(states({ import: 'done', review: 'active' }))
    expect(m.activeIndex).toBe(1)
  })

  it('organization is non-decreasing as stages complete', () => {
    const keys: StageKey[] = ['import', 'review', 'align', 'train', 'view', 'export']
    let prev = -1
    for (let done = 0; done <= 6; done++) {
      const map: Partial<Record<StageKey, StageState>> = {}
      for (let i = 0; i < done; i++) map[keys[i]] = 'done'
      const m = deriveLogoMotion(states(map))
      expect(m.organization).toBeGreaterThanOrEqual(prev)
      prev = m.organization
    }
  })

  it('all done → fully organized and solid, no active', () => {
    const m = deriveLogoMotion(
      states({ import: 'done', review: 'done', align: 'done', train: 'done', view: 'done', export: 'done' }),
    )
    expect(m.organization).toBe(1)
    expect(m.solid).toBe(1)
    expect(m.activeIndex).toBe(-1)
  })

  it('flags failure', () => {
    const m = deriveLogoMotion(states({ import: 'done', review: 'failed' }))
    expect(m.failed).toBe(true)
  })
})

describe('logoRampColor', () => {
  it('spans tan → amber → sage', () => {
    expect(logoRampColor(0)).toBe('rgb(196, 164, 132)')
    expect(logoRampColor(0.5)).toBe('rgb(200, 144, 47)')
    expect(logoRampColor(1)).toBe('rgb(168, 187, 163)')
  })

  it('clamps out-of-range input', () => {
    expect(logoRampColor(-1)).toBe(logoRampColor(0))
    expect(logoRampColor(2)).toBe(logoRampColor(1))
  })
})
