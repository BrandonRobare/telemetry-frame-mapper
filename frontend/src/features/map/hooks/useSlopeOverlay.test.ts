// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createElement, type ReactNode } from 'react'
import { cleanup, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { Job } from '../../../types/api'
import { latestCompletedReconstructionId, parseSlopeBounds, useSlopeOverlay } from './useSlopeOverlay'

function job(id: number, sessionId: number): Job {
  return {
    id,
    type: 'reconstruction',
    session_id: sessionId,
    source_session_ids: null,
    status: 'complete',
    preset: 'quick',
    progress_pct: 100,
    step: 'Complete',
    frames_used: 10,
    started_at: null,
    completed_at: null,
    error_msg: null,
  }
}

describe('slope overlay helpers', () => {
  it('uses the newest completed reconstruction for the current session', () => {
    expect(latestCompletedReconstructionId([job(9, 2), job(8, 1)], 2)).toBe(9)
    expect(latestCompletedReconstructionId([job(9, 2)], 1)).toBeNull()
  })

  it('accepts only ordered geographic bounds from the slope endpoint', () => {
    expect(parseSlopeBounds('[[40,-80],[41,-79]]')).toEqual([[40, -80], [41, -79]])
    expect(() => parseSlopeBounds('[[41,-80],[40,-79]]')).toThrow('invalid geographic bounds')
    expect(() => parseSlopeBounds(null)).toThrow('did not include geographic bounds')
  })
})

// jsdom implements neither of these, so the tests below install their own.
const realCreateObjectURL = URL.createObjectURL
const realRevokeObjectURL = URL.revokeObjectURL
const revoked: string[] = []

function stubObjectUrls() {
  let minted = 0
  URL.createObjectURL = vi.fn(() => `blob:slope-${++minted}`)
  URL.revokeObjectURL = vi.fn((url: string) => void revoked.push(url))
}

function stubSlopeApi() {
  const fetchMock = vi.fn((input: string) => {
    if (input.startsWith('/jobs/')) {
      return Promise.resolve(new Response(JSON.stringify([job(9, 2)]), {
        headers: { 'content-type': 'application/json' },
      }))
    }
    if (input === '/export/reconstructions/9/slope') {
      return Promise.resolve(new Response(new Blob(['slope-png']), {
        headers: { 'X-Slope-Bounds': '[[40,-80],[41,-79]]' },
      }))
    }
    return Promise.reject(new Error(`Unexpected request: ${input}`))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  URL.createObjectURL = realCreateObjectURL
  URL.revokeObjectURL = realRevokeObjectURL
  revoked.length = 0
})

describe('useSlopeOverlay object URL lifecycle', () => {
  it('mints a live object URL from the cached blob when the Map tab is remounted', async () => {
    stubObjectUrls()
    const fetchMock = stubSlopeApi()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client }, children)

    const first = renderHook(() => useSlopeOverlay(2, true), { wrapper })
    await waitFor(() => expect(first.result.current.data).toBeTruthy())
    const firstUrl = first.result.current.data?.imageUrl
    expect(firstUrl).toBeTruthy()

    // Leaving the Map tab unmounts the hook and revokes the URL it minted.
    first.unmount()
    expect(revoked).toEqual([firstUrl])

    // Coming back inside gcTime is served from cache — and must not hand back the dead URL.
    const second = renderHook(() => useSlopeOverlay(2, true), { wrapper })
    await waitFor(() => expect(second.result.current.data).toBeTruthy())
    const overlay = second.result.current.data

    expect(overlay?.imageUrl).toBeTruthy()
    expect(revoked).not.toContain(overlay?.imageUrl)
    expect(overlay?.imageUrl).not.toBe(firstUrl)
    expect(overlay?.bounds).toEqual([[40, -80], [41, -79]])
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/slope'))).toHaveLength(1)
  })
})
