import { describe, expect, it, vi, afterEach } from 'vitest'
import { apiUrl, get, resolveApiBaseUrl, shareUrl } from './client'

describe('API URL resolver', () => {
  it('uses a nonblank trimmed VITE_API_URL', () => {
    expect(resolveApiBaseUrl({ viteApiUrl: ' https://build.example/ ' }))
      .toBe('https://build.example')
  })

  it('defaults to same-origin when VITE_API_URL is blank', () => {
    expect(resolveApiBaseUrl({ viteApiUrl: '   ' })).toBe('')
  })

  it('defaults API requests to a same-origin relative path', () => {
    expect(apiUrl('/health')).toBe('/health')
  })

  it('uses the frontend origin for copied share links', () => {
    vi.stubGlobal('location', { origin: 'https://mapper.example.test' })
    expect(shareUrl('/view/share/share-token')).toBe('https://mapper.example.test/view/share/share-token')
  })
})

describe('api client errors', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('uses JSON detail as the error message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Import folder not found' }), {
      status: 404,
      headers: { 'content-type': 'application/json' },
    })))

    await expect(get('/missing')).rejects.toThrow('Import folder not found')
    expect(fetch).toHaveBeenCalledWith('/missing', expect.objectContaining({ credentials: 'include' }))
  })

  it('uses JSON message as the error message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ message: 'Bad request' }), {
      status: 400,
      headers: { 'content-type': 'application/json' },
    })))

    await expect(get('/bad')).rejects.toThrow('Bad request')
  })
})
