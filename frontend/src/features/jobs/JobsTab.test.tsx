// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import JobsTab from './JobsTab'
import { ErrorBoundary } from '../../ErrorBoundary'
import type { Job, SystemResources } from '../../types/api'

vi.mock('../../shared/api/reconstructionStatusEvents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../shared/api/reconstructionStatusEvents')>()),
  useReconstructionStatusEvents: () => undefined,
}))

const resources: SystemResources = {
  cpu_pct: 0,
  ram_used_gb: 0,
  ram_total_gb: 1,
  disk_used_gb: 0,
  disk_total_gb: 1,
  disk_io_mbps: null,
  gpu_pct: null,
  vram_used_gb: null,
  vram_total_gb: null,
  gpu_name: null,
  gpu_available: false,
  colmap_available: false,
  gsplat_available: false,
  tools: [],
  workflows: [],
}

const cancellingJob: Job = {
  id: 654,
  type: 'reconstruction',
  session_id: 12,
  source_session_ids: null,
  status: 'cancelling',
  preset: 'balanced',
  progress_pct: 42,
  step: 'Stopping reconstruction',
  frames_used: 120,
  started_at: '2026-08-12T00:00:00Z',
  completed_at: null,
  error_msg: null,
}

/** 25 finished jobs, newest id first — the order `/jobs/` returns them in. */
const historyFixture: Job[] = Array.from({ length: 25 }, (_, index) => {
  const id = 25 - index
  return {
    ...cancellingJob,
    id,
    session_id: id,
    status: id % 2 === 0 ? 'complete' : 'failed',
    step: 'Finished',
    completed_at: '2026-08-12T00:10:00Z',
    error_msg: id === 12 ? 'CUDA out of memory' : null,
  }
})

/** Stand-in for `GET /jobs/`: honours skip/limit/status the way the router does. */
function paginatedJobs(url: string): Job[] {
  const query = new URLSearchParams(url.slice(url.indexOf('?') + 1))
  const skip = Number(query.get('skip'))
  const limit = Number(query.get('limit'))
  // backend/routers/jobs.py declares limit as Query(50, ge=1, le=200).
  if (limit > 200) throw new Error(`limit=${limit} exceeds the backend maximum of 200`)
  const status = query.get('status')
  const matching = status ? historyFixture.filter((job) => job.status === status) : historyFixture
  return matching.slice(skip, skip + limit)
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function renderJobsTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <JobsTab />
      </QueryClientProvider>
    </ErrorBoundary>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('JobsTab reconstruction statuses', () => {
  it('renders a cancelling job in the Active list without firing the root ErrorBoundary', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.startsWith('/jobs/?')) return jsonResponse([cancellingJob])
      if (url === '/system/resources') return jsonResponse(resources)
      throw new Error(`Unexpected request: ${url}`)
    }))

    renderJobsTab()

    expect(await screen.findByText('Cancelling')).toBeTruthy()
    expect(screen.getByText('Active (1)')).toBeTruthy()
    expect(screen.queryByText('Render error. Check console for details')).toBeNull()
  })

  it('renders a running_remote job in the Active list, not History', async () => {
    const remoteJob: Job = { ...cancellingJob, id: 900, status: 'running_remote', step: 'Remote worker: training' }
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.startsWith('/jobs/?')) return jsonResponse([remoteJob])
      if (url === '/system/resources') return jsonResponse(resources)
      throw new Error(`Unexpected request: ${url}`)
    }))

    renderJobsTab()

    // `selector` skips the same-labelled <option> in the History status filter.
    expect(await screen.findByText('Remote', { selector: 'span' })).toBeTruthy()
    expect(screen.getByText('Active (1)')).toBeTruthy()
    expect(screen.queryByText('Render error. Check console for details')).toBeNull()
  })

  it('renders an unrecognized status as its raw label instead of crashing', async () => {
    const unknownStatusJob = { ...cancellingJob, id: 655, status: 'waiting_for_operator' } as unknown as Job
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.startsWith('/jobs/?')) return jsonResponse([unknownStatusJob])
      if (url === '/system/resources') return jsonResponse(resources)
      throw new Error(`Unexpected request: ${url}`)
    }))

    renderJobsTab()

    expect(await screen.findByText('waiting_for_operator')).toBeTruthy()
    expect(screen.queryByText('Render error. Check console for details')).toBeNull()
  })
})

describe('JobsTab history search', () => {
  function renderWithHistory() {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.startsWith('/jobs/?')) return jsonResponse(paginatedJobs(url))
      if (url === '/system/resources') return jsonResponse(resources)
      throw new Error(`Unexpected request: ${url}`)
    }))
    renderJobsTab()
  }

  async function search(needle: string) {
    const input = await screen.findByLabelText('Search job history')
    fireEvent.change(input, { target: { value: needle } })
  }

  it('matches a job that is not on the loaded page', async () => {
    renderWithHistory()
    // Job 12 is the 14th row, so page 1 never contains it.
    expect(await screen.findByRole('table')).toBeTruthy()
    expect(screen.queryByText('CUDA out of memory')).toBeNull()

    await search('CUDA out of memory')

    expect(await screen.findByText('CUDA out of memory')).toBeTruthy()
  })

  it('keeps a full page of rows while a search is active', async () => {
    renderWithHistory()
    expect(await screen.findByRole('table')).toBeTruthy()

    // 13 of the 25 jobs failed, so a search for them fills page 1 and spills onto page 2.
    await search('failed')

    // header + 10 jobs
    await waitFor(() => expect(screen.getAllByRole('row')).toHaveLength(11))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Page 2')).toBeTruthy()
    // header + the remaining 3
    await waitFor(() => expect(screen.getAllByRole('row')).toHaveLength(4))
  })
})
