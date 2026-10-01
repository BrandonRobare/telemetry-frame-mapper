// level: component; area: ingest-import
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import BulkSessionOperations from './BulkSessionOperations'
import { jsonResponse, mockApi, renderWithQuery } from '../../test/api'
import type { Session } from '../../types/api'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('posts selected IDs and tags, reports partial failure, and retains only failed selections', async () => {
  const fetchMock = mockApi((url, init) => {
    if (url === '/projects') return jsonResponse([])
    if (url === '/sessions/bulk' && init?.method === 'POST') return jsonResponse({ operation: 'add_tags', outcomes: [{ session_id: 1, ok: true }, { session_id: 2, ok: false, error: 'Session locked' }] })
    throw new Error(`Unexpected request: ${url}`)
  })
  renderWithQuery(<BulkSessionOperations sessions={[{ id: 1, name: 'North field' }, { id: 2, name: 'South field' }] as Session[]} />)
  await userEvent.click(screen.getByText('Bulk'))
  await userEvent.click(screen.getByRole('button', { name: 'All' }))
  await userEvent.type(screen.getByLabelText('Bulk session tags'), 'survey, repeat')
  await userEvent.click(screen.getByRole('button', { name: 'Add' }))
  expect(await screen.findByText('#2: Session locked')).toBeTruthy()
  expect(JSON.parse(String(fetchMock.mock.calls.find(([url]) => url === '/sessions/bulk')?.[1]?.body))).toEqual({ operation: 'add_tags', session_ids: [1, 2], tags: ['survey', 'repeat'] })
  expect((screen.getByRole('checkbox', { name: 'North field' }) as HTMLInputElement).checked).toBe(false)
  expect((screen.getByRole('checkbox', { name: 'South field' }) as HTMLInputElement).checked).toBe(true)
})

it('requires explicit DELETE confirmation before posting a destructive request', async () => {
  const fetchMock = mockApi((url, init) => {
    if (url === '/projects') return jsonResponse([])
    if (url === '/sessions/bulk' && init.method === 'POST') return jsonResponse({ operation: 'delete', outcomes: [{ session_id: 1, ok: true }] })
    throw new Error(`Unexpected request: ${url}`)
  })
  renderWithQuery(<BulkSessionOperations sessions={[{ id: 1, name: 'North field' }] as Session[]} />)
  await userEvent.click(screen.getByText('Bulk'))
  await userEvent.click(screen.getByRole('checkbox', { name: 'North field' }))
  const remove = screen.getByRole('button', { name: 'Delete' })
  expect((remove as HTMLButtonElement).disabled).toBe(true)
  await userEvent.type(screen.getByLabelText('Confirm bulk delete'), 'DELETE')
  await userEvent.click(remove)
  expect(await screen.findByText('1 completed')).toBeTruthy()
  const request = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
  expect(JSON.parse(String(request?.[1]?.body))).toEqual({ operation: 'delete', session_ids: [1], confirm: 'DELETE' })
})
