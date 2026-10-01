// level: component; area: flight-log-gps
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SessionLogTab from './SessionLogTab'
import { jsonResponse, mockApi, renderWithQuery } from '../../test/api'
import { useMapStore } from '../../shared/stores/mapStore'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); useMapStore.setState({ selectedSessionId: null, requestedTab: null }) })

it('offers overview navigation without making session requests when no session is selected', async () => {
  const fetchMock = mockApi(() => { throw new Error('Unexpected request') })
  renderWithQuery(<SessionLogTab />)
  await userEvent.click(screen.getByRole('button', { name: 'Open Overview' }))
  expect(useMapStore.getState().requestedTab).toBe('overview')
  expect(fetchMock).not.toHaveBeenCalled()
})

it('loads timeline entries newest first alongside flight and defect sections', async () => {
  useMapStore.setState({ selectedSessionId: 4 })
  mockApi((url) => {
    if (url === '/session-log?session_id=4') return jsonResponse([
      { id: 1, event_type: 'import_complete', timestamp: '2026-09-01T10:00:00Z', message: 'Imported images' },
      { id: 2, event_type: 'coverage_run', timestamp: '2026-09-02T10:00:00Z', message: 'Coverage ready', coverage_pct: 89 },
    ])
    return jsonResponse([])
  })
  renderWithQuery(<SessionLogTab />)
  await screen.findByText('Coverage ready')
  const table = screen.getByRole('table')
  const rows = within(table).getAllByRole('row')
  expect(rows[1].textContent).toContain('Coverage ready')
  expect(rows[2].textContent).toContain('Imported images')
  expect(screen.getByText('89.0%')).toBeTruthy()
})

it('renders a failed log request', async () => {
  useMapStore.setState({ selectedSessionId: 4 })
  mockApi((url) => jsonResponse(url.startsWith('/session-log') ? { detail: 'Unavailable' } : [], url.startsWith('/session-log') ? 503 : 200))
  renderWithQuery(<SessionLogTab />)
  expect(await screen.findByText('Failed to load session log.')).toBeTruthy()
})
