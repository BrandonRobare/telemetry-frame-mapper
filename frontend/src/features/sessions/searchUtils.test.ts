import { describe, expect, it } from 'vitest'
import { buildSessionSearchPath, sourceLabel } from './searchUtils'

describe('session search helpers', () => {
  it('builds the FTS endpoint with an optional source filter', () => {
    expect(buildSessionSearchPath('north roof', '')).toBe('/sessions/search?q=north+roof')
    expect(buildSessionSearchPath('crack', 'defect')).toBe('/sessions/search?q=crack&source=defect')
  })

  it('uses compact labels for result snippets', () => {
    expect(sourceLabel('session')).toBe('Session')
    expect(sourceLabel('log')).toBe('Log')
    expect(sourceLabel('defect')).toBe('Defect')
  })
})
