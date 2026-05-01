import { create } from 'zustand'

interface ActiveLayers {
  footprints: boolean
  coverage: boolean
  heatmap: boolean
  targetArea: boolean
}

interface MapStore {
  selectedSessionId: number | null
  activeLayers: ActiveLayers
  theme: 'dark' | 'light'
  sidebarOpen: boolean
  setSession: (id: number | null) => void
  toggleLayer: (key: keyof ActiveLayers) => void
  toggleTheme: () => void
  toggleSidebar: () => void
}

function applyTheme(theme: 'dark' | 'light') {
  document.documentElement.dataset.theme = theme
  localStorage.setItem('theme', theme)
}

const savedTheme = (localStorage.getItem('theme') as 'dark' | 'light' | null) ?? 'dark'
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
}))
