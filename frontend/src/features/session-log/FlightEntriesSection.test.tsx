// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import FlightEntriesSection from './FlightEntriesSection'
import { useToast } from '../../shared/hooks/useToast'
import type { FlightEntry } from '../../types/api'

const entry: FlightEntry = {
  id: 4,
  session_id: 1,
  battery_id: 'B-12',
  start_pct: 98,
  end_pct: 24,
  duration_s: 720,
  notes: 'windy',
  created_at: '2026-01-02T03:04:05Z',
}

const DELETE_PATH = '/sessions/1/flight-entries/4'
const DELETE_BUTTON = 'Delete battery B-12'

/** Stubs the list fetch; `onDelete` decides what the DELETE returns. */
function stubFetch(onDelete: () => Response) {
  const deleteCalls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/sessions/1/flight-entries' && !init?.method) {
      return new Response(JSON.stringify([entry]), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }
    if (url === DELETE_PATH && init?.method === 'DELETE') {
      deleteCalls.push(url)
      return onDelete()
    }
    throw new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url}`)
  }))
  return deleteCalls
}

function renderSection() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <FlightEntriesSection sessionId={1} />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useToast.setState({ toasts: [] })
})

describe('FlightEntriesSection delete', () => {
  it('names the entry it acts on and does not delete until the dialog is confirmed', async () => {
    const deleteCalls = stubFetch(() => new Response(null, { status: 204 }))
    renderSection()

    fireEvent.click(await screen.findByRole('button', { name: DELETE_BUTTON }))

    await screen.findByRole('alertdialog')
    expect(deleteCalls).toEqual([])

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(deleteCalls).toEqual([])
    expect(screen.queryByRole('alertdialog')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: DELETE_BUTTON }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete entry' }))
    await waitFor(() => expect(deleteCalls).toEqual([DELETE_PATH]))
  })

  it('reports a refused delete and leaves the entry on screen', async () => {
    stubFetch(() => new Response(JSON.stringify({ detail: 'Flight entry is locked' }), {
      status: 409,
      headers: { 'content-type': 'application/json' },
    }))
    renderSection()

    fireEvent.click(await screen.findByRole('button', { name: DELETE_BUTTON }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete entry' }))

    await waitFor(() => {
      expect(useToast.getState().toasts).toEqual([
        expect.objectContaining({ message: 'Flight entry is locked', type: 'error' }),
      ])
    })
    expect(screen.getByText('B-12')).toBeTruthy()
    expect(screen.getByRole('button', { name: DELETE_BUTTON })).toBeTruthy()
  })
})
