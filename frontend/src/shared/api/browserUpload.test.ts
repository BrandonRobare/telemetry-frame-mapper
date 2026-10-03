// level: unit; area: ingest-import
import { afterEach, expect, it, vi } from 'vitest'
import { uploadBrowserImport } from './browserUpload'

afterEach(() => vi.unstubAllGlobals())

it('reports a missing completed session without cancelling an import that succeeded', async () => {
  const requests: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    requests.push(url)
    const data = url.endsWith('/start')
      ? { upload_id: 'upload-1', chunk_size: 4, max_file_bytes: 10, max_total_bytes: 10, quota_bytes: 10 }
      : url.endsWith('/complete') ? { upload_id: 'upload-1', status: 'importing', session: null } : {}
    return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }))
  const file = new File(['test'], 'frame.jpg')
  await expect(uploadBrowserImport({ name: 'contract', files: [{ file, path: file.name }] }))
    .rejects.toThrow('Imported session is no longer available')
  expect(requests).toEqual([
    '/uploads/imports/start', '/uploads/imports/upload-1/chunk', '/uploads/imports/upload-1/complete',
  ])
})
