import { describe, expect, it } from 'vitest'
import { formatCoveragePct } from './coverageSummary'

describe('ExportTab coverage summary', () => {
  it('formats coverage percent when a coverage run exists', () => {
    expect(formatCoveragePct(87.4)).toBe('87%')
    expect(formatCoveragePct(87.5)).toBe('88%')
  })

  it('keeps N/A for sessions without a coverage result', () => {
    expect(formatCoveragePct(null)).toBe('N/A')
    expect(formatCoveragePct(undefined)).toBe('N/A')
  })
})
