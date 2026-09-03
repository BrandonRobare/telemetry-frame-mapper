// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AnnotationsList } from './SplatViewerTab'
import { useToast } from '../../shared/hooks/useToast'
import type { Annotation } from '../../types/api'

const annotation: Annotation = {
  id: 3,
  reconstruction_id: 9,
  label: 'Cracked pier',
  lat: 40,
  lon: -105,
  alt_m: 12,
  color: '#ff0000',
  created_at: '2026-01-02T03:04:05Z',
}

const DELETE_PATH = '/reconstruction/9/annotations/3'
const DELETE_BUTTON = 'Delete annotation Cracked pier'

function stubFetch(onDelete: () => Response) {
  const deleteCalls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url === DELETE_PATH && init?.method === 'DELETE') {
      deleteCalls.push(url)
      return onDelete()
    }
    throw new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url}`)
  }))
  return deleteCalls
}

function renderList() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <AnnotationsList reconstructionId={9} annotations={[annotation]} />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useToast.setState({ toasts: [] })
})

describe('AnnotationsList delete', () => {
  it('names the annotation it acts on and does not delete until the dialog is confirmed', async () => {
    const deleteCalls = stubFetch(() => new Response(null, { status: 204 }))
    renderList()

    fireEvent.click(screen.getByRole('button', { name: DELETE_BUTTON }))

    await screen.findByRole('alertdialog')
    expect(deleteCalls).toEqual([])

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(deleteCalls).toEqual([])
    expect(screen.queryByRole('alertdialog')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: DELETE_BUTTON }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete annotation' }))
    await waitFor(() => expect(deleteCalls).toEqual([DELETE_PATH]))
  })

  it('reports a refused delete and leaves the annotation on screen', async () => {
    stubFetch(() => new Response(JSON.stringify({ detail: 'Annotation is locked' }), {
      status: 409,
      headers: { 'content-type': 'application/json' },
    }))
    renderList()

    fireEvent.click(screen.getByRole('button', { name: DELETE_BUTTON }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete annotation' }))

    await waitFor(() => {
      expect(useToast.getState().toasts).toEqual([
        expect.objectContaining({ message: 'Annotation is locked', type: 'error' }),
      ])
    })
    expect(screen.getByText('Cracked pier')).toBeTruthy()
    expect(screen.getByRole('button', { name: DELETE_BUTTON })).toBeTruthy()
  })
})
