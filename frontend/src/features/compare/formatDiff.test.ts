import { describe, expect, it } from 'vitest'
import type { ComparisonDiff } from '../../types/api'
import { formatComparisonSummary, normalizeCellsForOverlay, visibleComparisonCells } from './formatDiff'

const diff: ComparisonDiff = {
  comparison: {
    session_a_id: 1,
    session_b_id: 2,
    reconstruction_a_id: 10,
    reconstruction_b_id: 11,
  },
  voxel_size_m: 1,
  utm_zone: '17N',
  summary: {
    a_cells: 2,
    b_cells: 2,
    new_count: 1,
    removed_count: 1,
  },
  new: [{ x: 10, y: 20, z: 0, size: 1, type: 'new' }],
  removed: [{ x: 30, y: 40, z: 0, size: 1, type: 'removed' }],
}

describe('comparison diff helpers', () => {
  it('formats summary counts', () => {
    expect(formatComparisonSummary(diff)).toBe('1 new · 1 removed')
  })

  it('filters visible layers', () => {
    expect(visibleComparisonCells(diff, true, false)).toEqual(diff.new)
    expect(visibleComparisonCells(diff, false, true)).toEqual(diff.removed)
    expect(visibleComparisonCells(diff, false, false)).toEqual([])
  })

  it('normalizes cells into overlay coordinates', () => {
    const normalized = normalizeCellsForOverlay([...diff.new, ...diff.removed])
    expect(normalized).toHaveLength(2)
    expect(normalized[0].overlayX).toBeGreaterThanOrEqual(4)
    expect(normalized[0].overlayX).toBeLessThanOrEqual(96)
    expect(normalized[1].overlayY).toBeGreaterThanOrEqual(4)
    expect(normalized[1].overlayY).toBeLessThanOrEqual(96)
  })
})
