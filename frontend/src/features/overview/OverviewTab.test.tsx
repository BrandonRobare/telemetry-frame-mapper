// level: component; area: platform-ops
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import OverviewTab from './OverviewTab'
import { jsonResponse, mockApi, renderWithQuery } from '../../test/api'
import { useMapStore } from '../../shared/stores/mapStore'

vi.mock('../hero/ReconstructionLogo3D', () => ({ default: () => null }))
afterEach(() => { cleanup(); vi.unstubAllGlobals(); useMapStore.setState({ selectedSessionId: null }) })

it('offers an import action when no session is selected', async () => {
  mockApi(() => jsonResponse([]))
  const onImport = vi.fn()
  renderWithQuery(<OverviewTab onImport={onImport} />)
  await userEvent.click(screen.getByRole('button', { name: 'Import a flight' }))
  expect(onImport).toHaveBeenCalledTimes(1)
  expect(screen.getByText('No session yet')).toBeTruthy()
})

it('renders selected session and coverage summary from API responses', async () => {
  useMapStore.setState({ selectedSessionId: 4 })
  mockApi((url) => {
    if (url === '/sessions/4') return jsonResponse({ id: 4, name: 'Field survey', photo_count: 42, usable_count: 38 })
    if (url === '/coverage/results?session_id=4') return jsonResponse({ coverage_pct: 87.4 })
    if (url === '/sessions/4/quick-report') return jsonResponse(null)
    if (url === '/jobs/') return jsonResponse([])
    throw new Error(`Unexpected request: ${url}`)
  })
  renderWithQuery(<OverviewTab />)
  expect(await screen.findByText('Session · Field survey')).toBeTruthy()
  expect(await screen.findByText('87%')).toBeTruthy()
  expect(screen.getByText('42')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Import a flight' })).toBeNull()
})
