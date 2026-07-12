import { describe, expect, it, beforeEach, vi } from 'vitest'

// ---------------------------------------------------------------------------
// Mock localStorage for node test environment
// ---------------------------------------------------------------------------
const store: Record<string, string> = {}
const localStorageMock = {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => { store[key] = value },
  removeItem: (key: string) => { delete store[key] },
  clear: () => { for (const k in store) delete store[k] },
}
vi.stubGlobal('localStorage', localStorageMock)

// Import AFTER stubbing localStorage so the store initializes with the mock
const { useChecklistStore, STORAGE_KEY } = await import('./checklistStore')
const { createDefaultChecklist } = await import('./checklist')

describe('checklistStore', () => {
  beforeEach(() => {
    localStorageMock.clear()
    useChecklistStore.setState({ items: createDefaultChecklist() })
  })

  it('initializes from defaults when localStorage is empty', () => {
    const items = useChecklistStore.getState().items
    expect(items.length).toBeGreaterThan(0)
    expect(items.every((i) => i.checked === false)).toBe(true)
  })

  it('toggle flips an item and persists to localStorage', () => {
    const { toggle } = useChecklistStore.getState()
    const id = useChecklistStore.getState().items[0].id
    toggle(id)
    expect(useChecklistStore.getState().items.find((i) => i.id === id)?.checked).toBe(true)

    const stored = JSON.parse(localStorageMock.getItem(STORAGE_KEY) ?? '[]')
    expect(stored.find((i: { id: string }) => i.id === id).checked).toBe(true)
  })

  it('add appends a custom item and persists it', () => {
    const { add } = useChecklistStore.getState()
    add('Spare props packed', 'pre-flight')
    const items = useChecklistStore.getState().items
    const added = items.find((i) => i.label === 'Spare props packed')
    expect(added).toBeDefined()
    expect(added?.custom).toBe(true)
    expect(added?.group).toBe('pre-flight')

    const stored = JSON.parse(localStorageMock.getItem(STORAGE_KEY) ?? '[]')
    expect(stored.some((i: { label: string }) => i.label === 'Spare props packed')).toBe(true)
  })

  it('add assigns unique ids across multiple calls', () => {
    const { add } = useChecklistStore.getState()
    add('Item A', 'pre-flight')
    add('Item B', 'pre-flight')
    const custom = useChecklistStore.getState().items.filter((i) => i.custom)
    expect(custom.length).toBe(2)
    expect(custom[0].id).not.toBe(custom[1].id)
  })

  it('remove deletes an item and persists the change', () => {
    const { add, remove } = useChecklistStore.getState()
    add('Temp item', 'post-flight')
    const id = useChecklistStore.getState().items.find((i) => i.label === 'Temp item')!.id
    remove(id)
    expect(useChecklistStore.getState().items.find((i) => i.id === id)).toBeUndefined()

    const stored = JSON.parse(localStorageMock.getItem(STORAGE_KEY) ?? '[]')
    expect(stored.find((i: { id: string }) => i.id === id)).toBeUndefined()
  })

  it('reset unchecks everything but keeps custom items, and persists', () => {
    const { toggle, add, reset } = useChecklistStore.getState()
    add('Custom check', 'pre-flight')
    const state = useChecklistStore.getState()
    toggle(state.items[0].id)
    toggle(state.items.find((i) => i.label === 'Custom check')!.id)

    reset()
    const items = useChecklistStore.getState().items
    expect(items.every((i) => i.checked === false)).toBe(true)
    expect(items.some((i) => i.label === 'Custom check')).toBe(true)

    const stored = JSON.parse(localStorageMock.getItem(STORAGE_KEY) ?? '[]')
    expect(stored.every((i: { checked: boolean }) => i.checked === false)).toBe(true)
  })
})
