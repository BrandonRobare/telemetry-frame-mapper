import type { Session } from '../../types/api'
import { apiUrl } from './client'

export interface BrowserUploadFilePlan {
  file: File
  path: string
}

export interface BrowserUploadProgress {
  uploadId: string
  uploadedBytes: number
  totalBytes: number
  status: 'starting' | 'uploading' | 'importing' | 'cancelled'
}

export interface BrowserUploadResult {
  session: Session
  uploadId: string
}

export interface BrowserUploadOptions {
  name: string
  files: BrowserUploadFilePlan[]
  signal?: AbortSignal
  onProgress?: (progress: BrowserUploadProgress) => void
}

interface StartUploadResponse {
  upload_id: string
  chunk_size: number
  max_file_bytes: number
  max_total_bytes: number
  quota_bytes: number
}

interface CompleteUploadResponse {
  upload_id: string
  status: string
  session: Session
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json() as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // Fall back below.
  }
  return `Upload failed with API error ${res.status}`
}

function throwIfAborted(signal?: AbortSignal) {
  if (signal?.aborted) throw new DOMException('Upload cancelled', 'AbortError')
}

async function checkedFetch<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), { credentials: 'include', ...init })
  if (!res.ok) throw new Error(await readError(res))
  return res.json() as Promise<T>
}

export function browserUploadDisplayPath(file: File): string {
  const withRelativePath = file as File & { webkitRelativePath?: string }
  return withRelativePath.webkitRelativePath || file.name
}

export function summarizeBrowserUpload(files: BrowserUploadFilePlan[]) {
  return {
    count: files.length,
    totalBytes: files.reduce((sum, item) => sum + item.file.size, 0),
  }
}

export async function uploadBrowserImport({ name, files, signal, onProgress }: BrowserUploadOptions): Promise<BrowserUploadResult> {
  if (files.length === 0) throw new Error('Choose at least one image to upload')
  const totalBytes = files.reduce((sum, item) => sum + item.file.size, 0)
  onProgress?.({ uploadId: '', uploadedBytes: 0, totalBytes, status: 'starting' })

  const start = await checkedFetch<StartUploadResponse>('/uploads/imports/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      total_bytes: totalBytes,
      files: files.map(({ file, path }) => ({ path, size: file.size })),
    }),
    signal,
  })

  let uploadedBytes = 0
  try {
    for (const { file, path } of files) {
      let offset = 0
      while (offset < file.size) {
        throwIfAborted(signal)
        const chunk = file.slice(offset, Math.min(file.size, offset + start.chunk_size))
        const form = new FormData()
        form.append('path', path)
        form.append('offset', String(offset))
        form.append('chunk', chunk, file.name)
        await checkedFetch(`/uploads/imports/${start.upload_id}/chunk`, {
          method: 'POST',
          body: form,
          signal,
        })
        offset += chunk.size
        uploadedBytes += chunk.size
        onProgress?.({ uploadId: start.upload_id, uploadedBytes, totalBytes, status: 'uploading' })
      }
    }

    const completed = await checkedFetch<CompleteUploadResponse>(`/uploads/imports/${start.upload_id}/complete`, {
      method: 'POST',
      signal,
    })
    onProgress?.({ uploadId: start.upload_id, uploadedBytes, totalBytes, status: 'importing' })
    return { session: completed.session, uploadId: completed.upload_id }
  } catch (error) {
    await fetch(apiUrl(`/uploads/imports/${start.upload_id}/cancel`), {
      method: 'POST',
      credentials: 'include',
    }).catch(() => undefined)
    throw error
  }
}
