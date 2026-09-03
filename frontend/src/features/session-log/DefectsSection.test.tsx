// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import DefectsSection from './DefectsSection'
import { useToast } from '../../shared/hooks/useToast'
import type { Defect } from '../../types/api'

const defect: Defect = {
  id: 7,
  session_id: 1,
  category: 'crack',
  severity: 'high',
  note: 'north face',
  created_at: '2026-01-02T03:04:05Z',
  image_ids: [],
  images: [],
}

const DELETE_PATH = '/sessions/1/defects/7'
const DELETE_BUTTON = 'Delete Crack defect: north face'

/** Stubs the list fetch; `onDelete` decides what the DELETE returns. */
function stubFetch(onDelete: () => Response) {
  const deleteCalls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/sessions/1/defects' && !init?.method) {
      return new Response(JSON.stringify([defect]), {
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
      <DefectsSection sessionId={1} />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useToast.setState({ toasts: [] })
})

describe('DefectsSection delete', () => {
  it('names the defect it acts on and does not delete until the dialog is confirmed', async () => {
    const deleteCalls = stubFetch(() => new Response(null, { status: 204 }))
    renderSection()

    fireEvent.click(await screen.findByRole('button', { name: DELETE_BUTTON }))

    // Dialog is up, nothing sent yet.
    await screen.findByRole('alertdialog')
    expect(deleteCalls).toEqual([])

    // Cancelling leaves the defect alone.
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(deleteCalls).toEqual([])
    expect(screen.queryByRole('alertdialog')).toBeNull()

    // Confirming sends it.
    fireEvent.click(screen.getByRole('button', { name: DELETE_BUTTON }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete defect' }))
    await waitFor(() => expect(deleteCalls).toEqual([DELETE_PATH]))
  })

  it('reports a refused delete and leaves the defect on screen', async () => {
    stubFetch(() => new Response(JSON.stringify({ detail: 'Defect is referenced by a report' }), {
      status: 409,
      headers: { 'content-type': 'application/json' },
    }))
    renderSection()

    fireEvent.click(await screen.findByRole('button', { name: DELETE_BUTTON }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete defect' }))

    await waitFor(() => {
      expect(useToast.getState().toasts).toEqual([
        expect.objectContaining({ message: 'Defect is referenced by a report', type: 'error' }),
      ])
    })
    expect(screen.getByText('north face')).toBeTruthy()
    expect(screen.getByRole('button', { name: DELETE_BUTTON })).toBeTruthy()
  })
})
