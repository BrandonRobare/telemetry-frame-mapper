// level: component; area: coverage-planning
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import MapTab from './MapTab'
import { jsonResponse, mockApi, renderWithQuery } from '../../test/api'
import { useMapStore } from '../../shared/stores/mapStore'

// Canvas/Leaflet rendering needs a browser layout; keep the tab's queries and state real.
vi.mock('../hero/GlassHero3D', () => ({ default: ({ onImport }: { onImport: () => void }) => <button onClick={onImport}>Import flight</button> }))
vi.mock('./LeafletMap', () => ({ default: ({ footprints, error }: { footprints: unknown[]; error: Error | null }) => <div role="status">{error ? error.message : `${footprints.length} mapped frames`}</div> }))
vi.mock('./SessionSidebar', () => ({ default: ({ session }: { session?: { name: string } }) => <aside>{session?.name}</aside> }))
afterEach(() => { cleanup(); vi.unstubAllGlobals(); useMapStore.setState({ selectedSessionId: null, sidebarOpen: true }) })

it('opens import from the landing hero', async () => {
  const onImport = vi.fn()
  renderWithQuery(<MapTab onImport={onImport} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Import flight' }))
  expect(onImport).toHaveBeenCalledTimes(1)
})

it('loads the selected session, shows live import progress, and collapses its sidebar', async () => {
  useMapStore.setState({ selectedSessionId: 4, sidebarOpen: true })
  mockApi((url) => {
    if (url === '/sessions/4') return jsonResponse({ id: 4, name: 'Field map' })
    if (url === '/sessions/4/progress') return jsonResponse({ status: 'running', processed: 2, total: 8 })
    if (url.startsWith('/footprints?')) return jsonResponse([{ id: 1 }])
    if (url.startsWith('/coverage/results')) return jsonResponse(null)
    throw new Error(`Unexpected request: ${url}`)
  })
  renderWithQuery(<MapTab />)
  expect(await screen.findByText('Field map')).toBeTruthy()
  expect(await screen.findByText(/2\/8 frames mapped/)).toBeTruthy()
  expect(await screen.findByRole('status')).toBeTruthy()
  await userEvent.click(screen.getByTitle('Collapse sidebar'))
  expect(useMapStore.getState().sidebarOpen).toBe(false)
})
