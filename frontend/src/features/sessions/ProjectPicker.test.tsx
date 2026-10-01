// level: component; area: ingest-import
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ProjectPicker from './ProjectPicker'
import { useMapStore } from '../../shared/stores/mapStore'
import { jsonResponse, mockApi, renderWithQuery } from '../../test/api'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); useMapStore.setState({ selectedProjectId: null, selectedSessionId: null }) })

it('selects the first loaded project, clears the session when switching, and creates a named project', async () => {
  const fetchMock = mockApi((url, init) => {
    if (url === '/projects/' && init?.method === 'POST') return jsonResponse({ id: 3, name: 'Bridge' })
    if (url === '/projects') return jsonResponse([{ id: 1, name: 'North' }, { id: 2, name: 'South' }])
    throw new Error(`Unexpected request: ${url}`)
  })
  renderWithQuery(<ProjectPicker />)
  const select = await screen.findByRole('combobox')
  await waitFor(() => expect(useMapStore.getState().selectedProjectId).toBe(1))
  useMapStore.setState({ selectedSessionId: 20 })
  await userEvent.selectOptions(select, '2')
  expect(useMapStore.getState()).toMatchObject({ selectedProjectId: 2, selectedSessionId: null })
  await userEvent.selectOptions(select, '__new__')
  const name = screen.getByRole('textbox', { name: 'New project name' })
  expect(document.activeElement).toBe(name)
  await userEvent.type(name, ' Bridge {Enter}')
  await waitFor(() => expect(useMapStore.getState().selectedProjectId).toBe(3))
  const request = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
  expect(JSON.parse(String(request?.[1]?.body))).toEqual({ name: 'Bridge' })
})
