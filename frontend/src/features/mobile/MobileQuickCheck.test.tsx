// level: component; area: coverage-planning
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import MobileQuickCheck from './MobileQuickCheck'
import { jsonResponse, mockApi, renderWithQuery } from '../../test/api'
import { useMapStore } from '../../shared/stores/mapStore'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); useMapStore.setState({ selectedSessionId: null }) })

it('auto-selects a session and updates its status and jobs when the operator changes selection', async () => {
  const sessions = [{ id: 1, name: 'North', photo_count: 20, usable_count: 18 }, { id: 2, name: 'South', photo_count: 42, usable_count: 38 }]
  mockApi((url) => {
    if (url === '/sessions') return jsonResponse(sessions)
    if (url === '/sessions/1' || url === '/sessions/2') return jsonResponse(sessions[Number(url.slice(-1)) - 1])
    if (url.endsWith('/quick-report')) return jsonResponse(null)
    if (url.startsWith('/coverage/results')) return jsonResponse(null)
    if (url === '/jobs/') return jsonResponse([{ id: 8, session_id: 2, status: 'failed', progress_pct: 25, step: 'Alignment failed', started_at: null }])
    throw new Error(`Unexpected request: ${url}`)
  })
  renderWithQuery(<MobileQuickCheck />)
  const picker = await screen.findByRole('combobox', { name: 'Select session' })
  await waitFor(() => expect(useMapStore.getState().selectedSessionId).toBe(1))
  expect(await screen.findByText('20')).toBeTruthy()
  await userEvent.selectOptions(picker, '2')
  expect(useMapStore.getState().selectedSessionId).toBe(2)
  expect(await screen.findByText('42')).toBeTruthy()
  const jobs = screen.getByRole('heading', { name: "This session's jobs" }).closest('section')!
  expect(await within(jobs).findByText('Failed')).toBeTruthy()
  expect(within(jobs).getByText('Session 2 · #8')).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Full app →' }).getAttribute('href')).toBe('/')
})
