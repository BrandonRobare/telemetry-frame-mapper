// @vitest-environment jsdom
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ReviewTab from './ReviewTab'
import { useMapStore } from '../../shared/stores/mapStore'

const image = {
  id: 1,
  session_id: 42,
  filename: 'frame-001.jpg',
  filepath: '/imports/frame-001.jpg',
  thumb_path: null,
  timestamp: null,
  latitude: null,
  longitude: null,
  altitude_m: null,
  original_latitude: null,
  original_longitude: null,
  original_altitude_m: null,
  synced_latitude: null,
  synced_longitude: null,
  synced_altitude_m: null,
  gps_source: 'exif',
  yaw: null,
  gimbal_pitch: null,
  width: null,
  height: null,
  focal_length_mm: null,
  sharpness_score: null,
  brightness_score: null,
  colmap_error_px: null,
  flag: 'good' as const,
  usable: true,
  notes: null,
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function renderReviewTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ReviewTab />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useMapStore.setState({ selectedSessionId: null })
  // The Review filters deep-link into the URL; do not carry them into the next test.
  window.history.replaceState(null, '', window.location.pathname)
})

describe('ReviewTab frame selection clearing', () => {
  it('does not clear on Escape outside the grid and requires confirmation before persisting a clear', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/images?session_id=42') return jsonResponse([image])
      if (url === '/reconstruction/frame-selection/42') return jsonResponse({ image_ids: [1] })
      if (url === '/reconstruction/frame-selection' && init?.method === 'POST') return jsonResponse(undefined)
      throw new Error(`Unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    useMapStore.setState({ selectedSessionId: 42 })

    renderReviewTab()
    await screen.findByText('1 selected for reconstruction')

    await userEvent.keyboard('{Escape}')
    expect(fetchMock).not.toHaveBeenCalledWith(
      '/reconstruction/frame-selection',
      expect.objectContaining({ method: 'POST' }),
    )

    const grid = document.querySelector('.fm-review-grid')
    if (!(grid instanceof HTMLDivElement)) throw new Error('Review grid not found')
    grid.focus()
    expect(document.activeElement).toBe(grid)
    grid.focus()
    await userEvent.keyboard('{Escape}')
    expect(await screen.findByRole('alertdialog')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalledWith(
      '/reconstruction/frame-selection',
      expect.objectContaining({ method: 'POST' }),
    )

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('alertdialog')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Clear' }))
    expect(screen.getByRole('alertdialog')).toBeTruthy()
    expect(screen.getByText('Clear reconstruction selection?')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalledWith(
      '/reconstruction/frame-selection',
      expect.objectContaining({ method: 'POST' }),
    )

    await userEvent.click(screen.getByRole('button', { name: 'Clear selection' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/reconstruction/frame-selection',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ session_id: 42, image_ids: [] }) }),
    ))
  })
})

describe('ReviewTab unscored frames', () => {
  function stubImages(images: unknown[]) {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/images?session_id=42') return jsonResponse(images)
      if (url === '/reconstruction/frame-selection/42') return jsonResponse({ image_ids: [] })
      throw new Error(`Unexpected request: ${url}`)
    }))
    useMapStore.setState({ selectedSessionId: 42 })
  }

  it('badges a frame whose quality scoring failed and offers it as a filter', async () => {
    stubImages([
      image,
      { ...image, id: 2, filename: 'frame-002.jpg', flag: 'unscored', usable: false },
    ])

    renderReviewTab()

    expect(await screen.findByRole('button', { name: 'Flag: Unscored, click to cycle' })).toBeTruthy()
    const filter = screen.getByRole('button', { name: /^1\s*Unscored$/ })
    await userEvent.click(filter)
    expect(screen.getByText('1 / 2 frames')).toBeTruthy()
    expect(screen.queryByText('frame-001.jpg')).toBeNull()
    expect(screen.getByText('frame-002.jpg')).toBeTruthy()
  })

  it('does not show the unscored filter when every frame was scored', async () => {
    stubImages([image])

    renderReviewTab()

    await screen.findByRole('button', { name: 'Flag: Good, click to cycle' })
    expect(screen.queryByRole('button', { name: /Unscored/ })).toBeNull()
  })
})
