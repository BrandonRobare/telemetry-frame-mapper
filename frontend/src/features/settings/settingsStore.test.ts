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
const { useSettingsStore } = await import('./settingsStore')

describe('settingsStore', () => {
  beforeEach(() => {
    localStorageMock.clear()
    // Reset store state to defaults
    useSettingsStore.setState({
      defaultTab: 'map',
      lastActiveTab: null,
      units: 'feet',
      coordFormat: 'decimal',
      coordPrecision: 6,
      reducedMotion: false,
      apiBaseUrl: '',
    })
  })

  it('initializes with sensible defaults', () => {
    const s = useSettingsStore.getState()
    expect(s.defaultTab).toBe('map')
    expect(s.lastActiveTab).toBe(null)
    expect(s.units).toBe('feet')
    expect(s.coordFormat).toBe('decimal')
    expect(s.coordPrecision).toBe(6)
    expect(s.reducedMotion).toBe(false)
    expect(s.apiBaseUrl).toBe('')
  })

  it('setUnits updates state and persists to localStorage', () => {
    const { setUnits } = useSettingsStore.getState()
    setUnits('meters')
    expect(useSettingsStore.getState().units).toBe('meters')
    const stored = JSON.parse(localStorageMock.getItem('gui-settings') ?? '{}')
    expect(stored.units).toBe('meters')
  })

  it('setCoordFormat persists to localStorage', () => {
    const { setCoordFormat } = useSettingsStore.getState()
    setCoordFormat('dms')
    expect(useSettingsStore.getState().coordFormat).toBe('dms')
    const stored = JSON.parse(localStorageMock.getItem('gui-settings') ?? '{}')
    expect(stored.coordFormat).toBe('dms')
  })

  it('setCoordPrecision persists to localStorage', () => {
    const { setCoordPrecision } = useSettingsStore.getState()
    setCoordPrecision(4)
    expect(useSettingsStore.getState().coordPrecision).toBe(4)
    const stored = JSON.parse(localStorageMock.getItem('gui-settings') ?? '{}')
    expect(stored.coordPrecision).toBe(4)
  })

  it('setReducedMotion persists to localStorage', () => {
    const { setReducedMotion } = useSettingsStore.getState()
    setReducedMotion(true)
    expect(useSettingsStore.getState().reducedMotion).toBe(true)
    const stored = JSON.parse(localStorageMock.getItem('gui-settings') ?? '{}')
    expect(stored.reducedMotion).toBe(true)
  })

  it('setDefaultTab persists to localStorage', () => {
    const { setDefaultTab } = useSettingsStore.getState()
    setDefaultTab('jobs')
    expect(useSettingsStore.getState().defaultTab).toBe('jobs')
    const stored = JSON.parse(localStorageMock.getItem('gui-settings') ?? '{}')
    expect(stored.defaultTab).toBe('jobs')
  })

  it('setLastActiveTab persists to localStorage', () => {
    const { setLastActiveTab } = useSettingsStore.getState()
    setLastActiveTab('review')
    expect(useSettingsStore.getState().lastActiveTab).toBe('review')
    const stored = JSON.parse(localStorageMock.getItem('gui-settings') ?? '{}')
    expect(stored.lastActiveTab).toBe('review')
  })

  it('setApiBaseUrl persists to localStorage', () => {
    const { setApiBaseUrl } = useSettingsStore.getState()
    setApiBaseUrl('http://myserver:9000')
    expect(useSettingsStore.getState().apiBaseUrl).toBe('http://myserver:9000')
    const stored = JSON.parse(localStorageMock.getItem('gui-settings') ?? '{}')
    expect(stored.apiBaseUrl).toBe('http://myserver:9000')
  })

  it('multiple mutations all persist', () => {
    const s = useSettingsStore.getState()
    s.setUnits('meters')
    s.setCoordFormat('dms')
    s.setCoordPrecision(3)
    const stored = JSON.parse(localStorageMock.getItem('gui-settings') ?? '{}')
    expect(stored.units).toBe('meters')
    expect(stored.coordFormat).toBe('dms')
    expect(stored.coordPrecision).toBe(3)
  })
})
