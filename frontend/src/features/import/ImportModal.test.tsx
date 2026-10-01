// level: component; area: ingest-import
import { useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ImportModal from './ImportModal'
import { jsonResponse, mockApi, renderWithQuery } from '../../test/api'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('focuses the name, traps focus at both ends, and restores focus after idle ESC', async () => {
  mockApi(() => jsonResponse({ status: 'ok' }))
  function Harness() {
    const [open, setOpen] = useState(false)
    return <><button onClick={() => setOpen(true)}>Import flight</button><ImportModal open={open} onClose={() => setOpen(false)} /></>
  }
  renderWithQuery(<Harness />)
  const trigger = screen.getByRole('button', { name: 'Import flight' })
  await userEvent.click(trigger)
  await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText('Session name')))
  screen.getByRole('button', { name: 'Close' }).focus()
  await userEvent.tab({ shift: true })
  expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Cancel' }))
  await userEvent.tab()
  expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Close' }))
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(trigger)
})

it('ignores ESC during upload, aborts the chunk on cancel, and cancels the reservation', async () => {
  let chunkSignal: AbortSignal | null = null
  const fetchMock = mockApi((url, init) => {
    if (url === '/health') return jsonResponse({ status: 'ok' })
    if (url === '/uploads/imports/start') return jsonResponse({ upload_id: 'upload-1', chunk_size: 1024 })
    if (url === '/uploads/imports/upload-1/chunk') {
      chunkSignal = init.signal as AbortSignal
      return new Promise((_resolve, reject) => chunkSignal!.addEventListener('abort', () => reject(new DOMException('Cancelled', 'AbortError'))))
    }
    if (url === '/uploads/imports/upload-1/cancel') return jsonResponse({ status: 'cancelled' })
    throw new Error(`Unexpected request: ${url}`)
  })
  const onClose = vi.fn()
  const { container } = renderWithQuery(<ImportModal open onClose={onClose} />)
  await userEvent.type(screen.getByLabelText('Session name'), 'Survey')
  // The native folder chooser is hidden; user-event supplies its FileList.
  await userEvent.upload(container.querySelector<HTMLInputElement>('input[type="file"]')!, new File(['jpeg'], 'frame.jpg', { type: 'image/jpeg' }))
  await userEvent.click(screen.getByRole('button', { name: 'Upload & Import' }))
  await waitFor(() => expect(chunkSignal).not.toBeNull())
  await userEvent.keyboard('{Escape}')
  expect(onClose).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Cancel upload' }))
  expect(chunkSignal!.aborted).toBe(true)
  expect(await screen.findByText('Upload cancelled.')).toBeTruthy()
  expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/cancel'))[0]?.[1]).toMatchObject({ method: 'POST', credentials: 'include' })
  expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/complete'))).toBe(false)
  await userEvent.keyboard('{Escape}')
  expect(onClose).toHaveBeenCalledTimes(1)
})
