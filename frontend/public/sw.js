// App-shell service worker for the PWA quick-check view (#364, #588).
//
// Navigation is network-first: online you always get the current build, and a
// successful response refreshes the cached shell. Offline you get that cached
// shell back — a navigation fallback, not offline operation. The hashed JS/CSS
// chunks are never cached, so a cold offline launch still needs the network to
// boot the app. No API caching, no offline data sync: this app is read-only and
// always wants fresh session/job data.

// The build version rides in on the registration URL (`/sw.js?v=<version>`,
// see src/main.tsx). A new version means a new worker URL, so the browser
// installs a fresh worker whose cache is a fresh name, and `activate` drops the
// previous release's shell.
const CACHE_NAME = `tfm-shell-${new URL(self.location.href).searchParams.get('v') || 'dev'}`

// Every navigation resolves to the same SPA document; cache it under one key.
const SHELL_URL = '/mobile'
const ASSET_URLS = ['/manifest.webmanifest', '/favicon.svg', '/pwa-icon.svg', '/pwa-icon-maskable.svg']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll([SHELL_URL, ...ASSET_URLS]))
      .then(() => self.skipWaiting())
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

// Same-origin GET only. Navigations are network-first with a cached-shell
// fallback; the unhashed shell assets stay cache-first; everything else
// (API calls, hashed build assets, non-GET) is left alone.
self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone()
            event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.put(SHELL_URL, copy)))
          }
          return response
        })
        .catch(() =>
          caches
            .open(CACHE_NAME)
            .then((cache) => cache.match(SHELL_URL))
            .then((cached) => cached || Response.error())
        )
    )
    return
  }

  if (!ASSET_URLS.includes(url.pathname)) return
  event.respondWith(caches.match(request).then((cached) => cached || fetch(request)))
})
