/**
 * Resolve the backend origin for every browser-facing API URL.
 *
 * A nonblank VITE_API_URL supports split frontend/backend deployments. An
 * empty result deliberately keeps the single-container build same-origin.
 */
export function resolveApiBaseUrl({
  viteApiUrl = import.meta.env.VITE_API_URL,
}: {
  viteApiUrl?: string
} = {}): string {
  const configured = viteApiUrl?.trim() || ''
  return configured.replace(/\/+$/, '')
}

/** Build a backend URL from the shared resolver. */
export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  const baseUrl = resolveApiBaseUrl()
  if (!baseUrl) return path
  return `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`
}

/** Build an absolute URL for a person to open on this frontend's origin. */
export function shareUrl(path: string): string {
  const relativePath = path.startsWith('/') ? path : `/${path}`
  const origin = globalThis.location?.origin
  return origin ? new URL(relativePath, origin).toString() : relativePath
}

async function errorMessage(res: Response): Promise<string> {
  const fallback = `API error ${res.status}`
  const contentType = res.headers.get('content-type') ?? ''
  const body = await res.text()
  if (!body) return fallback

  if (contentType.includes('application/json')) {
    try {
      const parsed = JSON.parse(body) as { detail?: unknown; message?: unknown; error?: unknown }
      const detail = parsed.detail ?? parsed.message ?? parsed.error
      if (typeof detail === 'string') return detail
      if (Array.isArray(detail)) {
        return detail
          .map((entry) => {
            if (typeof entry === 'string') return entry
            if (entry && typeof entry === 'object' && 'msg' in entry) return String(entry.msg)
            return JSON.stringify(entry)
          })
          .join('; ')
      }
      if (detail && typeof detail === 'object') return JSON.stringify(detail)
    } catch {
      // Fall through to the raw body below.
    }
  }

  return `${fallback}: ${body}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), { credentials: 'include', ...init })
  if (!res.ok) throw new Error(await errorMessage(res))
  if (res.status === 204 || res.headers.get('content-length') === '0') return undefined as T
  return res.json() as Promise<T>
}

export const get  = <T>(path: string) => request<T>(path)
export const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const patch = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const del  = <T>(path: string) => request<T>(path, { method: 'DELETE' })
