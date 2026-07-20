import { create } from 'zustand'

export type Theme = 'dark' | 'light'
export type BasemapId = string

interface ActiveLayers {
  footprints: boolean
  coverage: boolean
  heatmap: boolean
  slope: boolean
  targetArea: boolean
}

interface SyncedViewport {
  lat: number
  lon: number
  zoom: number
  source: 'leaflet' | '3d' | `comparison:${number}`
}

interface MapStore {
  selectedProjectId: number | null
  selectedSessionId: number | null
  activeLayers: ActiveLayers
  theme: Theme
  sidebarOpen: boolean
  basemapId: BasemapId
  slopeOpacity: number
  setBasemapId: (id: BasemapId) => void
  setSlopeOpacity: (opacity: number) => void
  setProject: (id: number | null) => void
  setSession: (id: number | null) => void
  toggleLayer: (key: keyof ActiveLayers) => void
  toggleTheme: () => void
  toggleSidebar: () => void
  requestedTab: string | null
  setRequestedTab: (tab: string | null) => void
  targetSessionId: number | null
  setTargetSessionId: (id: number | null) => void
  targetReconstructionId: number | null
  setTargetReconstructionId: (id: number | null) => void
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

function getSavedBasemap(): BasemapId {
  try {
    if (typeof localStorage === 'undefined') return 'esri_satellite'
    return localStorage.getItem('basemapId') || 'esri_satellite'
  } catch {
    return 'esri_satellite'
  }
}

function saveBasemap(id: BasemapId) {
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('basemapId', id)
    }
  } catch {
    // Ignore storage failures; the in-memory store still reflects the user's choice.
  }
}

export const useMapStore = create<MapStore>((set) => ({
  selectedProjectId: null,
  selectedSessionId: null,
  activeLayers: { footprints: true, coverage: true, heatmap: false, slope: false, targetArea: true },
  theme: savedTheme,
  sidebarOpen: true,
  basemapId: getSavedBasemap(),
  setBasemapId: (id) => set(() => {
    saveBasemap(id)
    return { basemapId: id }
  }),
  slopeOpacity: 0.65,
  setSlopeOpacity: (opacity) => set({ slopeOpacity: Math.min(1, Math.max(0, opacity)) }),

  setProject: (id) => set({ selectedProjectId: id }),

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
  targetReconstructionId: null,
  setTargetReconstructionId: (id) => set({ targetReconstructionId: id }),
  splitPaneActive: false,
  toggleSplitPane: () => set((s) => ({ splitPaneActive: !s.splitPaneActive })),
  syncedViewport: null,
  setSyncedViewport: (vp) => set({ syncedViewport: vp }),
}))
