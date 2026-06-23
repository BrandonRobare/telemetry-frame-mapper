import { create } from 'zustand'

export type Theme = 'dark' | 'light'

interface ActiveLayers {
  footprints: boolean
  coverage: boolean
  heatmap: boolean
  targetArea: boolean
}

interface SyncedViewport {
  lat: number
  lon: number
  zoom: number
  source: 'leaflet' | '3d'
}

interface MapStore {
  selectedSessionId: number | null
  activeLayers: ActiveLayers
  theme: Theme
  sidebarOpen: boolean
  setSession: (id: number | null) => void
  toggleLayer: (key: keyof ActiveLayers) => void
  toggleTheme: () => void
  toggleSidebar: () => void
  requestedTab: string | null
  setRequestedTab: (tab: string | null) => void
  targetSessionId: number | null
  setTargetSessionId: (id: number | null) => void
  splitPaneActive: boolean
  toggleSplitPane: () => void
  syncedViewport: SyncedViewport | null
  setSyncedViewport: (vp: SyncedViewport) => void
}

function isTheme(value: string | null): value is Theme {
  return value === 'dark' || value === 'light'
}

export function getSavedTheme(): Theme {
  try {
    if (typeof localStorage === 'undefined') return 'light'
    const saved = localStorage.getItem('theme')
    return isTheme(saved) ? saved : 'light'
  } catch {
    return 'light'
  }
}

function applyTheme(theme: Theme) {
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = theme
  }
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('theme', theme)
    }
  } catch {
    // Ignore storage failures; the in-memory store still reflects the user's choice.
  }
}

const savedTheme = getSavedTheme()
applyTheme(savedTheme)

export const useMapStore = create<MapStore>((set) => ({
  selectedSessionId: null,
  activeLayers: { footprints: true, coverage: true, heatmap: false, targetArea: true },
  theme: savedTheme,
  sidebarOpen: true,

  setSession: (id) => set({ selectedSessionId: id }),

  toggleLayer: (key) =>
    set((s) => ({ activeLayers: { ...s.activeLayers, [key]: !s.activeLayers[key] } })),

  toggleTheme: () =>
    set((s) => {
      const next = s.theme === 'dark' ? 'light' : 'dark'
      applyTheme(next)
      return { theme: next }
    }),

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),

  requestedTab: null,
  setRequestedTab: (tab) => set({ requestedTab: tab }),
  targetSessionId: null,
  setTargetSessionId: (id) => set({ targetSessionId: id }),
  splitPaneActive: false,
  toggleSplitPane: () => set((s) => ({ splitPaneActive: !s.splitPaneActive })),
  syncedViewport: null,
  setSyncedViewport: (vp) => set({ syncedViewport: vp }),
}))
