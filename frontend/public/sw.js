// Minimal app-shell service worker for the PWA quick-check view (#364).
// Scope is intentionally small: cache the shell so the icon/manifest/root
// respond even on a flaky field connection. No offline data sync, no API
// caching — this app is read-only and always wants fresh session/job data
// when a connection is available.

const CACHE_NAME = 'tfm-shell-v1'
const SHELL_URLS = ['/', '/mobile', '/manifest.webmanifest', '/favicon.svg', '/pwa-icon.svg', '/pwa-icon-maskable.svg']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_URLS)).then(() => self.skipWaiting())
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  )
})

// Cache-first for the app shell; everything else (API calls, hashed build
// assets) goes to the network untouched. Never intercepts non-GET requests.
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return
  const url = new URL(event.request.url)
  if (url.origin !== self.location.origin) return
  if (!SHELL_URLS.includes(url.pathname)) return

  event.respondWith(
    caches.match(event.request).then((cached) => cached ?? fetch(event.request))
  )
})
