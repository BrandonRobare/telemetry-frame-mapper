import { create } from 'zustand'

// ---------------------------------------------------------------------------
// GUI-only prefs — NOT in the backend contract — persisted to localStorage.
// ---------------------------------------------------------------------------

export type SettingsTab =
  | 'map'
  | 'gps-sync'
  | 'review'
  | 'plan'
  | 'export'
  | 'session-log'
  | 'reconstruct'
  | 'jobs'
  | 'storage'
  | 'splat'
  | 'compare'
  | 'settings'

export type Units = 'feet' | 'meters'
export type CoordFormat = 'decimal' | 'dms'

interface SettingsStore {
  defaultTab: SettingsTab
  units: Units
  coordFormat: CoordFormat
  coordPrecision: number
  reducedMotion: boolean
  apiBaseUrl: string

  setDefaultTab: (tab: SettingsTab) => void
  setUnits: (units: Units) => void
  setCoordFormat: (fmt: CoordFormat) => void
  setCoordPrecision: (n: number) => void
  setReducedMotion: (v: boolean) => void
  setApiBaseUrl: (url: string) => void
}

const STORAGE_KEY = 'gui-settings'

interface StoredPrefs {
  defaultTab?: SettingsTab
  units?: Units
  coordFormat?: CoordFormat
  coordPrecision?: number
  reducedMotion?: boolean
  apiBaseUrl?: string
}

function loadPrefs(): StoredPrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as StoredPrefs) : {}
  } catch {
    return {}
  }
}

function savePrefs(prefs: StoredPrefs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  } catch {
    // Quota exceeded or private browsing — silently ignore
  }
}

const saved = loadPrefs()

export const useSettingsStore = create<SettingsStore>((set, get) => ({
  defaultTab: saved.defaultTab ?? 'map',
  units: saved.units ?? 'feet',
  coordFormat: saved.coordFormat ?? 'decimal',
  coordPrecision: saved.coordPrecision ?? 6,
  reducedMotion: saved.reducedMotion ?? false,
  apiBaseUrl: saved.apiBaseUrl ?? '',

  setDefaultTab: (defaultTab) => {
    set({ defaultTab })
    savePrefs({ ...get(), defaultTab })
  },
  setUnits: (units) => {
    set({ units })
    savePrefs({ ...get(), units })
  },
  setCoordFormat: (coordFormat) => {
    set({ coordFormat })
    savePrefs({ ...get(), coordFormat })
  },
  setCoordPrecision: (coordPrecision) => {
    set({ coordPrecision })
    savePrefs({ ...get(), coordPrecision })
  },
  setReducedMotion: (reducedMotion) => {
    set({ reducedMotion })
    savePrefs({ ...get(), reducedMotion })
  },
  setApiBaseUrl: (apiBaseUrl) => {
    set({ apiBaseUrl })
    savePrefs({ ...get(), apiBaseUrl })
  },
}))
