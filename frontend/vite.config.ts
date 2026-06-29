import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const manualChunks = (id: string) => {
  if (!id.includes('node_modules')) return undefined
  if (id.includes('/react/') || id.includes('/react-dom/')) return 'react'
  if (id.includes('/@tanstack/react-query/')) return 'query'
  if (id.includes('/leaflet') || id.includes('/react-leaflet/')) return 'maps'
  if (id.includes('/@turf/')) return 'turf'
  if (id.includes('/@mkkellogg/gaussian-splats-3d/')) return 'splats'
  if (id.includes('/three/')) return 'three'
  return undefined
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks,
      },
    },
  },
  test: {
    environment: 'node',
    globals: true,
  },
})
