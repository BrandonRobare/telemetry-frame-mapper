// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import SessionSidebar from './SessionSidebar'
import { ToastStack } from '../../shared/components/ToastStack'
import { useToast } from '../../shared/hooks/useToast'
import type { Session, CoverageResult } from '../../types/api'

// framer-motion (via the glass panels + toast stack) reads matchMedia on mount.
beforeEach(() => {
  window.matchMedia ??= ((query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
    dispatchEvent() { return false },
  })) as unknown as typeof window.matchMedia
})

const SESSION: Session = {
  id: 1, name: 'Flight 1', folder_path: '/f', import_mode: 'copy',
  imported_at: '2026-01-01T00:00:00Z', photo_count: 10, usable_count: 8,
  notes: null, tags: [], project_id: null,
}

// A minimal fetch stub that records coverage/run calls and lets each test decide
// how POST /coverage/run resolves.
function stubFetch(coverageResponse: () => Response) {
  const calls: { url: string; method: string }[] = []
  const jsonRes = (body: unknown, ok = true, status = 200): Response =>
    ({
      ok, status,
      headers: { get: (k: string) => (k === 'content-type' ? 'application/json' : null) },
      text: async () => JSON.stringify(body),
      json: async () => body,
    }) as unknown as Response

  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url)
    const method = init?.method ?? 'GET'
    if (u.includes('/target-areas/')) return jsonRes([{ id: 7, name: 'North Field' }])
    if (u.includes('/coverage/run')) {
      calls.push({ url: u, method })
      return coverageResponse()
    }
    return jsonRes(null)
  }))
  return { calls, jsonRes }
}

function renderSidebar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <SessionSidebar session={SESSION} coverage={null} frameCount={5} />
      <ToastStack />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useToast.setState({ toasts: [] })
})

describe('SessionSidebar — run coverage', () => {
  it('POSTs /coverage/run with both session_id and target_area_id', async () => {
    const cov: CoverageResult = {
      id: 3, target_area_id: 7, session_ids: '1', covered_area_m2: 1,
      coverage_pct: 50, gap_geojson: null, overlap_geojson: null,
    } as CoverageResult
    const { calls, jsonRes } = stubFetch(() => jsonRes(cov))
    renderSidebar()

    // Target-area selector populates from GET /target-areas/.
    await screen.findByRole('option', { name: 'North Field' })
    fireEvent.click(screen.getByRole('button', { name: 'Run coverage analysis' }))

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].method).toBe('POST')
    expect(calls[0].url).toContain('session_id=1')
    expect(calls[0].url).toContain('target_area_id=7')
  })

  it('renders visible error feedback when the run fails', async () => {
    const { jsonRes } = stubFetch(() => jsonRes({ detail: 'target_area_id required' }, false, 422))
    renderSidebar()

    await screen.findByRole('option', { name: 'North Field' })
    fireEvent.click(screen.getByRole('button', { name: 'Run coverage analysis' }))

    // The error surfaces as a toast (role="status" live region), not a silent no-op.
    expect(await screen.findByText('target_area_id required')).toBeTruthy()
  })
})
