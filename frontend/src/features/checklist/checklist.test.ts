import { describe, expect, it } from 'vitest'
import {
  addItem,
  computeProgress,
  createDefaultChecklist,
  groupItems,
  removeItem,
  resetChecklist,
  toggleItem,
} from './checklist'

describe('createDefaultChecklist', () => {
  it('returns a non-empty list of unchecked items covering both groups', () => {
    const items = createDefaultChecklist()
    expect(items.length).toBeGreaterThan(0)
    expect(items.every((i) => i.checked === false)).toBe(true)
    expect(items.some((i) => i.group === 'pre-flight')).toBe(true)
    expect(items.some((i) => i.group === 'post-flight')).toBe(true)
    expect(items.every((i) => i.custom === false)).toBe(true)
  })

  it('has unique ids', () => {
    const items = createDefaultChecklist()
    const ids = new Set(items.map((i) => i.id))
    expect(ids.size).toBe(items.length)
  })
})

describe('toggleItem', () => {
  it('flips the checked state of the matching item only', () => {
    const items = createDefaultChecklist()
    const targetId = items[0].id
    const toggled = toggleItem(items, targetId)
    expect(toggled.find((i) => i.id === targetId)?.checked).toBe(true)
    expect(toggled.filter((i) => i.checked).length).toBe(1)

    const toggledBack = toggleItem(toggled, targetId)
    expect(toggledBack.find((i) => i.id === targetId)?.checked).toBe(false)
  })

  it('is a no-op for an unknown id', () => {
    const items = createDefaultChecklist()
    const result = toggleItem(items, 'does-not-exist')
    expect(result).toEqual(items)
  })

  it('does not mutate the input array', () => {
    const items = createDefaultChecklist()
    const snapshot = JSON.parse(JSON.stringify(items))
    toggleItem(items, items[0].id)
    expect(items).toEqual(snapshot)
  })
})

describe('addItem', () => {
  it('appends a new custom, unchecked item to the given group', () => {
    const items = createDefaultChecklist()
    const result = addItem(items, 'custom-1', '  Spare props packed  ', 'pre-flight')
    const added = result.find((i) => i.id === 'custom-1')
    expect(added).toEqual({
      id: 'custom-1',
      label: 'Spare props packed',
      group: 'pre-flight',
      checked: false,
      custom: true,
    })
    expect(result.length).toBe(items.length + 1)
  })

  it('ignores blank labels', () => {
    const items = createDefaultChecklist()
    const result = addItem(items, 'custom-2', '   ', 'post-flight')
    expect(result).toEqual(items)
  })
})

describe('removeItem', () => {
  it('removes the matching item', () => {
    const items = addItem(createDefaultChecklist(), 'custom-1', 'Extra check', 'pre-flight')
    const result = removeItem(items, 'custom-1')
    expect(result.find((i) => i.id === 'custom-1')).toBeUndefined()
    expect(result.length).toBe(items.length - 1)
  })

  it('is a no-op for an unknown id', () => {
    const items = createDefaultChecklist()
    const result = removeItem(items, 'does-not-exist')
    expect(result).toEqual(items)
  })
})

describe('resetChecklist', () => {
  it('unchecks every item but keeps them all (including custom ones)', () => {
    let items = createDefaultChecklist()
    items = addItem(items, 'custom-1', 'Extra check', 'pre-flight')
    items = toggleItem(items, items[0].id)
    items = toggleItem(items, 'custom-1')

    const result = resetChecklist(items)
    expect(result.every((i) => i.checked === false)).toBe(true)
    expect(result.length).toBe(items.length)
    expect(result.some((i) => i.id === 'custom-1')).toBe(true)
  })
})

describe('computeProgress', () => {
  it('reports 0/total with pct 0 when nothing is checked', () => {
    const items = createDefaultChecklist()
    const progress = computeProgress(items)
    expect(progress).toEqual({ total: items.length, completed: 0, pct: 0 })
  })

  it('reports completed/total and rounds pct', () => {
    let items = createDefaultChecklist()
    items = toggleItem(items, items[0].id)
    items = toggleItem(items, items[1].id)
    const progress = computeProgress(items)
    expect(progress.completed).toBe(2)
    expect(progress.total).toBe(items.length)
    expect(progress.pct).toBe(Math.round((2 / items.length) * 100))
  })

  it('handles an empty list without dividing by zero', () => {
    expect(computeProgress([])).toEqual({ total: 0, completed: 0, pct: 0 })
  })

  it('can scope progress to a single group', () => {
    const items = createDefaultChecklist()
    const preFlightCount = items.filter((i) => i.group === 'pre-flight').length
    const toggled = toggleItem(items, items.find((i) => i.group === 'pre-flight')!.id)
    const progress = computeProgress(toggled, 'pre-flight')
    expect(progress.total).toBe(preFlightCount)
    expect(progress.completed).toBe(1)
  })
})

describe('groupItems', () => {
  it('buckets items by group, preserving order', () => {
    const items = createDefaultChecklist()
    const grouped = groupItems(items)
    expect(grouped['pre-flight'].every((i) => i.group === 'pre-flight')).toBe(true)
    expect(grouped['post-flight'].every((i) => i.group === 'post-flight')).toBe(true)
    expect(grouped['pre-flight'].length + grouped['post-flight'].length).toBe(items.length)
  })
})
