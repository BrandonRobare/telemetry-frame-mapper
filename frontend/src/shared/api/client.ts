export const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

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
  const res = await fetch(`${API_BASE_URL}${path}`, { credentials: 'include', ...init })
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
