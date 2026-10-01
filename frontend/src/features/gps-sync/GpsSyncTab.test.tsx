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
    expect(url).toBe('/flight-logs/upload')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('include')
    expect(init.body).toBeInstanceOf(FormData)
    const body = init.body as FormData
    expect(body.get('file')).toBe(file)
    expect(body.get('session_id')).toBe('42')
    // An empty flight-start field sends nothing, so absolute-time logs upload as before.
    expect(body.has('start_time')).toBe(false)
  })

  it('sends the flight start field as a UTC ISO 8601 start_time when filled', async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
      async () => new Response('{}', { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    useMapStore.setState({ selectedSessionId: 42 })

    renderGpsSyncTab()
    fireEvent.change(screen.getByLabelText('Flight start (UTC)'), {
      target: { value: '2024-06-15T10:30:05' },
    })
    selectFlightLog(new File(['time(millisecond)\n'], 'flight.csv', { type: 'text/csv' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const body = fetchMock.mock.calls[0][1]?.body as FormData
    // Read as UTC whatever the browser's zone: 10:30:05 in the field is 10:30:05Z.
    expect(body.get('start_time')).toBe('2024-06-15T10:30:05.000Z')
  })

  it('shows the relative-clock 422 detail at the flight start field', async () => {
    const detail =
      'Flight log timestamps are relative to the start of the flight (0 s to 600 s) and the ' +
      "log does not record when the flight started. Upload it again with start_time set to the flight's UTC start."
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ detail }), {
        status: 422,
        headers: { 'content-type': 'application/json' },
      })),
    )
    useMapStore.setState({ selectedSessionId: 42 })

    renderGpsSyncTab()
    selectFlightLog(new File(['time(millisecond)\n'], 'flight.csv', { type: 'text/csv' }))

    const message = await screen.findByText(detail)
    expect(screen.getAllByText(detail)).toHaveLength(1)
    const input = screen.getByLabelText('Flight start (UTC)')
    expect(input.getAttribute('aria-invalid')).toBe('true')
    expect(input.getAttribute('aria-describedby')?.split(' ')).toContain(message.id)

    // Filling the field in clears the prompt.
    fireEvent.change(input, { target: { value: '2024-06-15T10:30' } })
    expect(screen.queryByText(detail)).toBeNull()
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
