// level: component; area: platform-ops
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SettingsTab from './SettingsTab'
import { jsonResponse, mockApi, renderWithQuery } from '../../test/api'
import { settingsFixture } from '../../test/settings'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); window.history.replaceState({}, '', '/') })

it('renders the selected settings form and updates the deep link when changing sections', async () => {
  mockApi(() => jsonResponse(settingsFixture))
  renderWithQuery(<SettingsTab />)
  expect(screen.getByRole('heading', { name: 'General' })).toBeTruthy()
  await userEvent.click(screen.getByRole('button', { name: 'Import & Ingest' }))
  expect(await screen.findByRole('heading', { name: 'Import & Ingest' })).toBeTruthy()
  expect(window.location.search).toContain('section=ingest')
  await userEvent.click(screen.getByRole('button', { name: 'Advanced' }))
  expect(await screen.findByText('Accepted Extensions')).toBeTruthy()
  await userEvent.click(screen.getByRole('button', { name: 'Advanced' }))
  await waitFor(() => expect(screen.queryByText('Accepted Extensions')).toBeNull())
})

it('shows invalid ingest input and does not PATCH it, then saves a corrected value', async () => {
  window.history.replaceState({}, '', '/?section=ingest')
  const fetchMock = mockApi(() => jsonResponse(settingsFixture))
  renderWithQuery(<SettingsTab />)
  // This form's numeric field has no programmatic label yet; use its native role.
  const size = screen.getByRole('spinbutton')
  await userEvent.clear(size)
  await userEvent.type(size, '0')
  expect(screen.getByText('Thumbnail size must be greater than 0')).toBeTruthy()
  const save = screen.getByRole('button', { name: 'Save changes' })
  expect((save as HTMLButtonElement).disabled).toBe(true)
  await userEvent.click(save)
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(false)
  await userEvent.clear(size)
  await userEvent.type(size, '256')
  await userEvent.click(save)
  const request = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
  expect(request?.[0]).toBe('/settings')
  expect(JSON.parse(String(request?.[1]?.body)).ingest.thumbnail_size_px).toBe(256)
})
