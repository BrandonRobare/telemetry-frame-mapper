import { describe, expect, it } from 'vitest'
import { filterReconstructionLogLines } from './logPanel'

describe('filterReconstructionLogLines', () => {
  const lines = [
    'COLMAP started',
    'Feature extraction complete',
    'ERROR: sparse reconstruction failed',
  ]

  it('returns every line for an empty filter', () => {
    expect(filterReconstructionLogLines(lines, '')).toEqual(lines)
    expect(filterReconstructionLogLines(lines, '   ')).toEqual(lines)
  })

  it('filters lines case-insensitively', () => {
    expect(filterReconstructionLogLines(lines, 'error')).toEqual([
      'ERROR: sparse reconstruction failed',
    ])
    expect(filterReconstructionLogLines(lines, 'colmap')).toEqual(['COLMAP started'])
  })
})
