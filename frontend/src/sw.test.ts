import { describe, it, expect, beforeEach } from 'vitest'
import swSource from '../public/sw.js?raw'

// sw.js is a classic service worker script, so it can't export anything. Run it
// with `self`, `caches` and `fetch` as injected parameters instead: the script
// body resolves those names to the fakes below, and the file stays a valid
// worker exactly as it ships.

const ORIGIN = 'https://tfm.test'
const VERSION = '9.9.9'
const CACHE_NAME = `tfm-shell-${VERSION}`

type Listener = (event: FetchEvent) => void
type FetchEvent = {
  request: Request
  respondWith: (response: Promise<Response> | Response) => void
  waitUntil: (work: Promise<unknown>) => void
}
type LifecycleListener = (event: { waitUntil: (work: Promise<unknown>) => void }) => void

let caches: Map<string, Map<string, Response>>
let listeners: Record<string, Listener>
let networkResponse: () => Promise<Response>
let networkCalls: string[]

const cacheFor = (name: string) => {
  if (!caches.has(name)) caches.set(name, new Map())
  const entries = caches.get(name)!
  const key = (k: string | Request) => (typeof k === 'string' ? k : new URL(k.url).pathname)
  return {
    addAll: async (urls: string[]) => {
      for (const url of urls) entries.set(url, new Response(`precached:${url}`))
    },
    put: async (k: string | Request, v: Response) => void entries.set(key(k), v),
    match: async (k: string | Request) => entries.get(key(k)),
  }
}

const cacheStorage = {
  open: async (name: string) => cacheFor(name),
  match: async (k: string | Request) => {
    for (const name of caches.keys()) {
      const hit = await cacheFor(name).match(k)
      if (hit) return hit
    }
    return undefined
  },
  keys: async () => [...caches.keys()],
  delete: async (name: string) => caches.delete(name),
}

const request = (url: string, init: { method?: string; mode?: string } = {}) =>
  ({ url, method: init.method ?? 'GET', mode: init.mode ?? 'no-cors' }) as unknown as Request

/** Dispatch a fetch event; resolves to the response served, or null if the worker passed it through. */
const dispatchFetch = async (req: Request) => {
  let served: Promise<Response> | Response | null = null
  const pending: Promise<unknown>[] = []
  listeners.fetch({
    request: req,
    respondWith: (r) => void (served = r),
    waitUntil: (w) => void pending.push(w),
  })
  const response = served === null ? null : await (served as Promise<Response> | Response)
  await Promise.all(pending)
  return response
}

const dispatchLifecycle = async (type: 'install' | 'activate') => {
  const pending: Promise<unknown>[] = []
  ;(listeners[type] as unknown as LifecycleListener)({ waitUntil: (p) => void pending.push(p) })
  await Promise.all(pending)
}

beforeEach(async () => {
  caches = new Map()
  listeners = {}
  networkCalls = []
  networkResponse = async () => new Response('fresh shell', { status: 200 })

  const self = {
    location: new URL(`${ORIGIN}/sw.js?v=${VERSION}`),
    addEventListener: (type: string, fn: Listener) => void (listeners[type] = fn),
    skipWaiting: async () => {},
    clients: { claim: async () => {} },
  }
  const fetchFn = async (req: Request) => {
    networkCalls.push(req.url)
    return networkResponse()
  }
  new Function('self', 'caches', 'fetch', swSource)(self, cacheStorage, fetchFn)

  // Install first, so the precached shell exists as it would on a real client.
  await dispatchLifecycle('install')
})

describe('cache versioning', () => {
  it('names the cache after the build version on the registration URL', () => {
    expect([...caches.keys()]).toEqual([CACHE_NAME])
  })

  it('drops another build’s cache on activate', async () => {
    caches.set('tfm-shell-1.0.0', new Map())
    await dispatchLifecycle('activate')
    expect([...caches.keys()]).toEqual([CACHE_NAME])
  })
})

describe('navigation requests', () => {
  it('serves the network response and refreshes the cached shell when online', async () => {
    const response = await dispatchFetch(request(`${ORIGIN}/mobile`, { mode: 'navigate' }))

    expect(await response!.text()).toBe('fresh shell')
    expect(networkCalls).toEqual([`${ORIGIN}/mobile`])
    expect(await (await cacheFor(CACHE_NAME).match('/mobile'))!.text()).toBe('fresh shell')
  })

  it('does not cache an error page returned by the server', async () => {
    networkResponse = async () => new Response('502 whoops', { status: 502 })
    await dispatchFetch(request(`${ORIGIN}/mobile`, { mode: 'navigate' }))

    expect(await (await cacheFor(CACHE_NAME).match('/mobile'))!.text()).toBe('precached:/mobile')
  })

  it('falls back to the cached shell when offline', async () => {
    networkResponse = () => Promise.reject(new TypeError('Failed to fetch'))
    const response = await dispatchFetch(request(`${ORIGIN}/`, { mode: 'navigate' }))

    expect(await response!.text()).toBe('precached:/mobile')
  })
})

describe('everything else', () => {
  it('leaves non-GET requests alone', async () => {
    const response = await dispatchFetch(request(`${ORIGIN}/api/jobs`, { method: 'POST' }))

    expect(response).toBeNull()
    expect(await cacheStorage.match(`${ORIGIN}/api/jobs`)).toBeUndefined()
  })

  it('leaves same-origin API GETs alone', async () => {
    const response = await dispatchFetch(request(`${ORIGIN}/api/sessions/1`))

    expect(response).toBeNull()
    expect(await cacheStorage.match(`${ORIGIN}/api/sessions/1`)).toBeUndefined()
  })

  it('leaves cross-origin requests alone', async () => {
    const response = await dispatchFetch(request('https://fonts.googleapis.com/css2?family=X'))

    expect(response).toBeNull()
  })

  it('leaves hashed build assets alone', async () => {
    const response = await dispatchFetch(request(`${ORIGIN}/assets/index-a1b2c3.js`))

    expect(response).toBeNull()
  })

  it('serves the unhashed shell assets from the cache', async () => {
    const response = await dispatchFetch(request(`${ORIGIN}/manifest.webmanifest`))

    expect(await response!.text()).toBe('precached:/manifest.webmanifest')
    expect(networkCalls).toEqual([])
  })
})
