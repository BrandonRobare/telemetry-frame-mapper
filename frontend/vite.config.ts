import { readFileSync } from 'node:fs'
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

// public/sw.js is copied verbatim and can't read the build manifest, so the
// version is handed to it on its registration URL (#588).
const version = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')).version

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: { __APP_VERSION__: JSON.stringify(version) },
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
