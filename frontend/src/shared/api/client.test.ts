import { describe, expect, it, vi, afterEach } from 'vitest'
import { get } from './client'

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
  })

  it('uses JSON message as the error message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ message: 'Bad request' }), {
      status: 400,
      headers: { 'content-type': 'application/json' },
    })))

    await expect(get('/bad')).rejects.toThrow('Bad request')
  })
})
