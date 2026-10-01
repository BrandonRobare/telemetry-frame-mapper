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

/**
 * A non-2xx API response. `message` is for people; branch on `status` or on
 * `code`, the machine-readable reason some endpoints send beside `detail`.
 */
export class ApiError extends Error {
  readonly status: number
  readonly code: string | null

  constructor(message: string, status: number, code: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

async function apiError(res: Response): Promise<ApiError> {
  const fallback = `API error ${res.status}`
  const contentType = res.headers.get('content-type') ?? ''
  const body = await res.text()
  if (!body) return new ApiError(fallback, res.status)

  if (contentType.includes('application/json')) {
    try {
      const parsed = JSON.parse(body) as {
        detail?: unknown
        message?: unknown
        error?: unknown
        code?: unknown
      }
      const code = typeof parsed.code === 'string' ? parsed.code : null
      const detail = parsed.detail ?? parsed.message ?? parsed.error
      if (typeof detail === 'string') return new ApiError(detail, res.status, code)
      if (Array.isArray(detail)) {
        const message = detail
          .map((entry) => {
            if (typeof entry === 'string') return entry
            if (entry && typeof entry === 'object' && 'msg' in entry) return String(entry.msg)
            return JSON.stringify(entry)
          })
          .join('; ')
        return new ApiError(message, res.status, code)
      }
      if (detail && typeof detail === 'object') {
        return new ApiError(JSON.stringify(detail), res.status, code)
      }
    } catch {
      // Fall through to the raw body below.
    }
  }

  return new ApiError(`${fallback}: ${body}`, res.status)
}

const DEFAULT_TIMEOUT_MS = 120_000

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // A wedged backend must not leave UI requests pending forever; time out
  // while still honouring any caller-supplied signal (#868).
  const controller = new AbortController()
  const timeout = setTimeout(() => {
    controller.abort(new DOMException('Request timed out', 'TimeoutError'))
  }, DEFAULT_TIMEOUT_MS)
  const outer = init?.signal
  if (outer) {
    if (outer.aborted) controller.abort()
    else outer.addEventListener('abort', () => controller.abort(), { once: true })
  }
  try {
    const res = await fetch(apiUrl(path), { credentials: 'include', ...init, signal: controller.signal })
    if (!res.ok) throw await apiError(res)
    if (res.status === 204 || res.headers.get('content-length') === '0') return undefined as T
    return res.json() as Promise<T>
  } finally {
    clearTimeout(timeout)
  }
}

export const get  = <T>(path: string) => request<T>(path)
export const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const patch = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const del  = <T>(path: string) => request<T>(path, { method: 'DELETE' })
