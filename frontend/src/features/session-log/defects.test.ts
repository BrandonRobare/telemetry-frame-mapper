import { describe, expect, it } from 'vitest'
import { CATEGORY_LABELS, SEVERITY_LABELS, formatCategoryLabel, severityColorVar } from './defects'

describe('formatCategoryLabel', () => {
  it('title-cases known categories from the shared label map', () => {
    expect(formatCategoryLabel('crack')).toBe('Crack')
    expect(formatCategoryLabel('water_damage')).toBe('Water damage')
    expect(formatCategoryLabel('missing_material')).toBe('Missing material')
  })

  it('falls back to a humanized underscore replacement for unknown categories', () => {
    expect(formatCategoryLabel('some_new_category' as never)).toBe('some new category')
  })

  it('has a label for every entry in CATEGORY_LABELS', () => {
    for (const key of Object.keys(CATEGORY_LABELS)) {
      expect(formatCategoryLabel(key as never).length).toBeGreaterThan(0)
    }
  })
})

describe('severityColorVar', () => {
  it('maps known severities to distinct CSS variables', () => {
    expect(severityColorVar('low')).toBe('var(--text-muted)')
    expect(severityColorVar('medium')).toBe('var(--warning)')
    expect(severityColorVar('high')).toBe('var(--danger)')
  })

  it('returns a neutral fallback for null severity', () => {
    expect(severityColorVar(null)).toBe('var(--text-faint)')
  })

  it('has an entry for every key in SEVERITY_LABELS', () => {
    for (const key of Object.keys(SEVERITY_LABELS)) {
      expect(severityColorVar(key as never)).toMatch(/^var\(--/)
    }
  })
})
