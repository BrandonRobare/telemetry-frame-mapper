import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'framer-motion'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from './ErrorBoundary.tsx'
import { useMapStore } from './shared/stores/mapStore'

if (import.meta.env.DEV) {
  ;(window as unknown as Record<string, unknown>).setSession =
    (id: number) => useMapStore.getState().setSession(id)
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

createRoot(document.getElementById('root')!).render(
  <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user">
        <App />
      </MotionConfig>
    </QueryClientProvider>
  </ErrorBoundary>,
)

// App-shell service worker for the PWA quick-check view (#364). Production-only:
// registering it in dev fights Vite's HMR module graph.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // Best-effort: the app works fully without it, just without shell caching.
    })
  })
}
