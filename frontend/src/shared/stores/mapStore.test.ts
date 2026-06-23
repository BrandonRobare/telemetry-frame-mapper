import { beforeEach, describe, expect, it, vi } from 'vitest'

const store: Record<string, string> = {}
const localStorageMock = {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => { store[key] = value },
  removeItem: (key: string) => { delete store[key] },
  clear: () => { for (const key in store) delete store[key] },
}
const documentMock = {
  documentElement: { dataset: {} as Record<string, string> },
}

vi.stubGlobal('localStorage', localStorageMock)
vi.stubGlobal('document', documentMock)

async function loadMapStore() {
  vi.resetModules()
  return await import('./mapStore')
}

describe('mapStore theme preference', () => {
  beforeEach(() => {
    localStorageMock.clear()
    documentMock.documentElement.dataset = {}
  })

  it('initializes from a saved dark theme and applies it to the document', async () => {
    localStorageMock.setItem('theme', 'dark')

    const { useMapStore } = await loadMapStore()

    expect(useMapStore.getState().theme).toBe('dark')
    expect(documentMock.documentElement.dataset.theme).toBe('dark')
  })

  it('falls back to light when saved theme is invalid', async () => {
    localStorageMock.setItem('theme', 'solarized')

    const { getSavedTheme, useMapStore } = await loadMapStore()

    expect(getSavedTheme()).toBe('light')
    expect(useMapStore.getState().theme).toBe('light')
    expect(localStorageMock.getItem('theme')).toBe('light')
  })

  it('toggleTheme updates state, document theme, and localStorage', async () => {
    const { useMapStore } = await loadMapStore()

    useMapStore.getState().toggleTheme()

    expect(useMapStore.getState().theme).toBe('dark')
    expect(documentMock.documentElement.dataset.theme).toBe('dark')
    expect(localStorageMock.getItem('theme')).toBe('dark')
  })
})
