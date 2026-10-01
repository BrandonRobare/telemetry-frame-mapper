// level: component; area: coverage-planning
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CompareTab from './CompareTab'
import { jsonResponse, mockApi, renderWithQuery } from '../../test/api'
import { useMapStore } from '../../shared/stores/mapStore'
import { useToast } from '../../shared/hooks/useToast'

// Leaflet requires layout and tiles; the tab still uses its real queries and selectors.
vi.mock('./CompareMapPane', () => ({ default: () => <div>Map context</div> }))
const jobs = [{ id: 11, session_id: 1, status: 'complete', preset: 'quick', frames_used: 10 }, { id: 22, session_id: 2, status: 'complete', preset: 'full', frames_used: 20 }]

afterEach(() => { cleanup(); vi.unstubAllGlobals(); useMapStore.setState({ selectedProjectId: null, selectedSessionId: null }); useToast.setState({ toasts: [] }) })

it('renders an empty state when there are fewer than two completed reconstructions', async () => {
  mockApi(() => jsonResponse([]))
  renderWithQuery(<CompareTab />)
  expect(await screen.findByText('At least two completed reconstructions are required.')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Compare' })).toBeNull()
})

function comparisonApi(status = 200) {
  return mockApi((url, init) => {
    if (url === '/sessions/') return jsonResponse([{ id: 1, name: 'Before' }, { id: 2, name: 'After' }])
    if (url === '/jobs/') return jsonResponse(jobs)
    if (url === '/comparisons' && init?.method === 'POST') return jsonResponse(status === 200 ? { id: 7, status: 'complete' } : { detail: 'Cannot compare unreferenced reconstructions' }, status)
    if (url === '/comparisons/7') return jsonResponse({ id: 7, status: 'complete' })
    if (url === '/comparisons/7/diff') return jsonResponse({ new: [], removed: [], summary: { new_count: 3, removed_count: 2 } })
    throw new Error(`Unexpected request: ${url}`)
  })
}

it('loads reconstructions, creates the selected comparison, and renders its diff download', async () => {
  const fetchMock = comparisonApi()
  renderWithQuery(<CompareTab />)
  await userEvent.selectOptions(await screen.findByLabelText('Baseline'), '22')
  await userEvent.selectOptions(screen.getByLabelText('Updated'), '11')
  await userEvent.click(screen.getByRole('button', { name: 'Compare' }))
  expect(await screen.findByText('3 new · 2 removed')).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Export GeoJSON' }).getAttribute('href')).toBe('/comparisons/7/diff.geojson')
  const request = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
  expect(JSON.parse(String(request?.[1]?.body))).toEqual({ session_a_id: 2, session_b_id: 1, reconstruction_a_id: 22, reconstruction_b_id: 11 })
})

it('reports a rejected comparison and leaves the action available for retry', async () => {
  comparisonApi(422)
  renderWithQuery(<CompareTab />)
  await userEvent.selectOptions(await screen.findByLabelText('Updated'), '22')
  await userEvent.click(screen.getByRole('button', { name: 'Compare' }))
  await waitFor(() => expect(useToast.getState().toasts.some((toast) => toast.message === 'Cannot compare unreferenced reconstructions')).toBe(true))
  expect(screen.queryByRole('link', { name: 'Export GeoJSON' })).toBeNull()
  expect((screen.getByRole('button', { name: 'Compare' }) as HTMLButtonElement).disabled).toBe(false)
})
