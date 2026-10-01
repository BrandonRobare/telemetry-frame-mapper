// level: component; area: reconstruction-splat
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SplatViewerTab from './SplatViewerTab'
import { jsonResponse, mockApi, renderWithQuery } from '../../test/api'
import { useMapStore } from '../../shared/stores/mapStore'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); useMapStore.setState({ selectedSessionId: null, requestedTab: null }) })

it('guides an operator with no selected session to Overview', async () => {
  mockApi(() => jsonResponse({ workflows: [] }))
  renderWithQuery(<SplatViewerTab />)
  expect(screen.getByRole('heading', { name: 'No session selected' })).toBeTruthy()
  await userEvent.click(screen.getByRole('button', { name: 'Open Overview' }))
  expect(useMapStore.getState().requestedTab).toBe('overview')
})

it('loads jobs for the session and explains when no reconstruction exists', async () => {
  useMapStore.setState({ selectedSessionId: 4 })
  const fetchMock = mockApi((url) => {
    if (url === '/jobs/') return jsonResponse([])
    if (url === '/system/resources') return jsonResponse({ workflows: [] })
    throw new Error(`Unexpected request: ${url}`)
  })
  renderWithQuery(<SplatViewerTab />)
  expect(await screen.findByText('No reconstructions for this session. Start one in the Reconstruct tab.')).toBeTruthy()
  expect(fetchMock.mock.calls.some(([url]) => url === '/jobs/')).toBe(true)
})

it('renders current-session training progress and waits for a completed reconstruction', async () => {
  useMapStore.setState({ selectedSessionId: 4 })
  mockApi((url) => {
    if (url === '/jobs/') return jsonResponse([
      { id: 8, session_id: 4, status: 'running_gsplat', preset: 'quick', progress_pct: 45, step: 'Training' },
      { id: 9, session_id: 5, status: 'complete', preset: 'full', progress_pct: 100 },
    ])
    if (url === '/system/resources') return jsonResponse({ workflows: [] })
    throw new Error(`Unexpected request: ${url}`)
  })
  renderWithQuery(<SplatViewerTab />)
  expect(await screen.findByText('#8 · quick')).toBeTruthy()
  expect(screen.getByText('45%')).toBeTruthy()
  expect(screen.getByText('Reconstruction in progress…')).toBeTruthy()
  expect(screen.queryByText('#9 · full')).toBeNull()
})
