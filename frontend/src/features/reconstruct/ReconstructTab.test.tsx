// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ReconstructTab from './ReconstructTab'
import { useMapStore } from '../../shared/stores/mapStore'
import type { Job } from '../../types/api'

vi.mock('../../shared/api/reconstructionStatusEvents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../shared/api/reconstructionStatusEvents')>()),
  useReconstructionStatusEvents: () => undefined,
}))

const remoteJob: Job = {
  id: 900,
  type: 'reconstruction',
  session_id: 42,
  source_session_ids: null,
  status: 'running_remote',
  preset: 'full',
  progress_pct: 37,
  step: 'Remote worker: training',
  frames_used: 210,
  started_at: '2026-08-25T00:00:00Z',
  completed_at: null,
  error_msg: null,
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function renderReconstructTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ReconstructTab />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useMapStore.setState({ selectedProjectId: null, selectedSessionId: null })
})

describe('ReconstructTab with a remote-worker reconstruction', () => {
  it('treats running_remote as a live job: progress card, Cancel, and start blocked', async () => {
    useMapStore.setState({ selectedProjectId: null, selectedSessionId: 42 })
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/jobs/') return jsonResponse([remoteJob])
      if (url === '/sessions') return jsonResponse([{ id: 42, name: 'Site A' }])
      if (url === '/target-areas/') return jsonResponse([])
      if (url.startsWith('/reconstruction/frame-selection/')) return jsonResponse({ image_ids: [1, 2] })
      // Preflight is not what this test is about; let it 404 so the card stays hidden.
      if (url.startsWith('/reconstruction/preflight/')) return new Response('nope', { status: 404 })
      throw new Error(`Unexpected request: ${url}`)
    }))

    renderReconstructTab()

    // Progress card for the live remote job.
    expect(await screen.findByText(/Reconstruction #900/)).toBeTruthy()
    expect(screen.getByText('Remote worker: training')).toBeTruthy()
    // Cancel button is offered.
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeTruthy()
    // Second start is blocked, not re-enabled.
    const start = screen.getByRole('button', { name: 'Reconstruction already in progress' })
    expect((start as HTMLButtonElement).disabled).toBe(true)
    expect(screen.queryByRole('button', { name: 'Start Reconstruction' })).toBeNull()
  })
})
