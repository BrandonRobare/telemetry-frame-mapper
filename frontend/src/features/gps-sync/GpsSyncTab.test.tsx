// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import GpsSyncTab from './GpsSyncTab'
import { useMapStore } from '../../shared/stores/mapStore'
import { useToast } from '../../shared/hooks/useToast'

function renderGpsSyncTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <GpsSyncTab />
    </QueryClientProvider>,
  )
}

function selectFlightLog(file: File) {
  const input = document.querySelector('input[type="file"]')
  if (!(input instanceof HTMLInputElement)) throw new Error('Flight log input not found')
  fireEvent.change(input, { target: { files: [file] } })
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useMapStore.setState({ selectedSessionId: null })
  useToast.setState({ toasts: [] })
})

describe('GpsSyncTab flight-log upload', () => {
  it('posts the file and session_id together as multipart form data', async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
      async () => new Response('{}', { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    useMapStore.setState({ selectedSessionId: 42 })

    renderGpsSyncTab()
    const file = new File(['time(millisecond),OSD.latitude,OSD.longitude,OSD.altitude[m]\n'], 'flight.csv', {
      type: 'text/csv',
    })
    selectFlightLog(file)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://localhost:8000/flight-logs/upload')
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    const body = init.body as FormData
    expect(body.get('file')).toBe(file)
    expect(body.get('session_id')).toBe('42')
  })

  it('shows the backend detail when the upload fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ detail: 'Session is not ready for GPS sync' }), {
        status: 422,
        headers: { 'content-type': 'application/json' },
      })),
    )
    useMapStore.setState({ selectedSessionId: 42 })

    renderGpsSyncTab()
    selectFlightLog(new File(['invalid'], 'flight.csv', { type: 'text/csv' }))

    expect(await screen.findByText('Session is not ready for GPS sync')).toBeTruthy()
  })
})
