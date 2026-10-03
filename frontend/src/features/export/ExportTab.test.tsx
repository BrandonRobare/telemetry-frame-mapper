// @vitest-environment jsdom
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ExportTab from './ExportTab'
import { formatCoveragePct } from './coverageSummary'
import { useMapStore } from '../../shared/stores/mapStore'
import { useToast } from '../../shared/hooks/useToast'
import type { Job, Session } from '../../types/api'

describe('ExportTab coverage summary', () => {
  it('formats coverage percent when a coverage run exists', () => {
    expect(formatCoveragePct(87.4)).toBe('87%')
    expect(formatCoveragePct(87.5)).toBe('88%')
  })

  it('keeps N/A for sessions without a coverage result', () => {
    expect(formatCoveragePct(null)).toBe('N/A')
    expect(formatCoveragePct(undefined)).toBe('N/A')
  })
})

const SESSION_ID = 7
const REC_ID = 5
const SHARE_LINKS = `/export/reconstructions/${REC_ID}/share-links`

const session: Session = {
  id: SESSION_ID,
  name: 'Bridge survey',
  folder_path: null,
  imported_at: '2026-09-01T10:00:00+00:00',
  photo_count: 12,
  usable_count: 10,
  notes: null,
  tags: [],
  project_id: null,
}

const job: Job = {
  id: REC_ID,
  type: 'reconstruction',
    effective_splat_settings: null,
  session_id: SESSION_ID,
  source_session_ids: null,
  status: 'complete',
  preset: 'quick',
  progress_pct: 100,
  step: 'done',
  frames_used: 10,
  started_at: null,
  completed_at: null,
  error_msg: null,
}

/** A share link as GET .../share-links returns it. */
interface ShareLinkRow {
  id: number
  reconstruction_id: number
  expires_at: string
  password_protected: boolean
  revoked_at: string | null
  created_at: string
}

function shareLink(id: number, overrides: Partial<ShareLinkRow> = {}): ShareLinkRow {
  return {
    id,
    reconstruction_id: REC_ID,
    expires_at: '2099-01-01T00:00:00+00:00',
    password_protected: false,
    revoked_at: null,
    created_at: '2026-09-29T12:00:00+00:00',
    ...overrides,
  }
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

interface ApiCall {
  method: string
  url: string
}

/**
 * Stubs the reads every Export tab render makes; `handle` answers anything else
 * (or overrides a read) and returns undefined to fall through to the defaults.
 */
function stubApi(handle: (call: ApiCall) => Response | Promise<Response> | undefined) {
  const calls: ApiCall[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const call = { method: init?.method ?? 'GET', url }
    calls.push(call)
    const handled = handle(call)
    if (handled) return handled
    if (call.method === 'GET') {
      if (url === `/sessions/${SESSION_ID}`) return jsonResponse(session)
      if (url === `/coverage/results?session_id=${SESSION_ID}`) return jsonResponse(null)
      if (url === '/jobs/') return jsonResponse([job])
      if (url === `/reconstruction/${REC_ID}/mesh/status`) {
        return jsonResponse({
          id: REC_ID, mesh_status: null, mesh_error: null,
          mesh_glb_path: null, mesh_obj_path: null, mesh_mtl_path: null,
        })
      }
      if (url === `/reconstruction/${REC_ID}/ortho/status`) {
        return jsonResponse({ id: REC_ID, ortho_status: null, ortho_error: null, ortho_path: null })
      }
      if (url === SHARE_LINKS) return jsonResponse([])
    }
    throw new Error(`Unexpected request: ${call.method} ${url}`)
  }))
  return calls
}

function renderExportTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ExportTab />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useMapStore.setState({ selectedSessionId: SESSION_ID })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  useToast.setState({ toasts: [] })
  useMapStore.setState({ selectedSessionId: null })
})

describe('ExportTab share links', () => {
  it('sends one POST when Generate Share Link is clicked twice', async () => {
    let links: ShareLinkRow[] = []
    let finishCreate: () => void = () => {}
    const calls = stubApi(({ method, url }) => {
      if (method === 'GET' && url === SHARE_LINKS) return jsonResponse(links)
      if (method === 'POST' && url === `/export/reconstructions/${REC_ID}/share-link`) {
        return new Promise<Response>((resolve) => {
          finishCreate = () => {
            links = [shareLink(21)]
            resolve(jsonResponse({
              share_token: 'tfm_new-token',
              share_link_id: 21,
              reconstruction_id: REC_ID,
              session_id: SESSION_ID,
              expires_at: '2099-01-01T00:00:00+00:00',
              password_protected: false,
            }, 201))
          }
        })
      }
      return undefined
    })
    renderExportTab()

    const generate = await screen.findByRole('button', { name: 'Generate Share Link' })
    await userEvent.dblClick(generate)
    await waitFor(() => expect((generate as HTMLButtonElement).disabled).toBe(true))
    await userEvent.click(generate)

    finishCreate()
    expect(await screen.findByText(/\/view\/share\/tfm_new-token$/)).toBeTruthy()
    // The new link is listed with its own Revoke control.
    expect(await screen.findByRole('button', { name: 'Revoke share link #21' })).toBeTruthy()
    expect(calls.filter((c) => c.method === 'POST')).toEqual([
      { method: 'POST', url: `/export/reconstructions/${REC_ID}/share-link` },
    ])
    expect((generate as HTMLButtonElement).disabled).toBe(false)
  })

  it('revokes a link through the revoke endpoint and removes its row', async () => {
    let links = [shareLink(12, { password_protected: true }), shareLink(13)]
    const revokeUrl = `${SHARE_LINKS}/12/revoke`
    const calls = stubApi(({ method, url }) => {
      if (method === 'GET' && url === SHARE_LINKS) return jsonResponse(links)
      if (method === 'POST' && url === revokeUrl) {
        links = links.map((link) =>
          link.id === 12 ? { ...link, revoked_at: '2026-09-30T08:00:00+00:00' } : link,
        )
        return jsonResponse(links[0])
      }
      return undefined
    })
    renderExportTab()

    await userEvent.click(await screen.findByRole('button', { name: 'Revoke share link #12' }))
    // Nothing is revoked until the dialog is confirmed.
    await screen.findByRole('alertdialog')
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Revoke link' }))

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Revoke share link #12' })).toBeNull(),
    )
    expect(screen.getByRole('button', { name: 'Revoke share link #13' })).toBeTruthy()
    expect(calls.filter((c) => c.method === 'POST')).toEqual([{ method: 'POST', url: revokeUrl }])
  })

  it('lists only links that still work', async () => {
    stubApi(({ method, url }) => {
      if (method === 'GET' && url === SHARE_LINKS) {
        return jsonResponse([
          shareLink(30),
          shareLink(31, { revoked_at: '2026-09-29T13:00:00+00:00' }),
          shareLink(32, { expires_at: '2020-01-01T00:00:00+00:00' }),
        ])
      }
      return undefined
    })
    renderExportTab()

    expect(await screen.findByRole('button', { name: 'Revoke share link #30' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Revoke share link #31' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Revoke share link #32' })).toBeNull()
  })
})

describe('ExportTab WebODM georeferencing CSV', () => {
  it('downloads the zip after the POST builds it', async () => {
    const downloadUrl = `/export/webodm-georeferencing-csv/download?session_id=${SESSION_ID}`
    const zipName = `webodm_georeferencing_csv_${SESSION_ID}.zip`
    const clicked: { href: string | null; download: string }[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push({ href: this.getAttribute('href'), download: this.download })
    })
    const calls = stubApi(({ method, url }) => {
      if (method === 'POST' && url === `/export/webodm-georeferencing-csv?session_id=${SESSION_ID}`) {
        return jsonResponse({ zip_path: `/srv/exports/${zipName}`, image_count: 10 })
      }
      return undefined
    })
    renderExportTab()

    await userEvent.click(await screen.findByRole('button', { name: 'Download georeferencing CSV zip' }))

    await waitFor(() => expect(clicked).toEqual([{ href: downloadUrl, download: zipName }]))
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(1)
    // A link to the same file stays in case the browser blocked the automatic download.
    const link = await screen.findByRole('link', { name: 'Download zip' })
    expect(link.getAttribute('href')).toBe(downloadUrl)
    expect(screen.getByText('Ready: 10 images')).toBeTruthy()
  })
})

// level: component; area: export-share
it('guides an operator without a selected session back to Overview', async () => {
  useMapStore.setState({ selectedSessionId: null })
  renderExportTab()
  await userEvent.click(screen.getByRole('button', { name: 'Open Overview' }))
  expect(useMapStore.getState().requestedTab).toBe('overview')
})

it('reports a rejected share-link creation and allows another attempt', async () => {
  stubApi(({ method, url }) => {
    if (method === 'POST' && url === `/export/reconstructions/${REC_ID}/share-link`) return jsonResponse({ detail: 'Share signing unavailable' }, 503)
    return undefined
  })
  renderExportTab()
  const generate = await screen.findByRole('button', { name: 'Generate Share Link' })
  await userEvent.click(generate)
  await waitFor(() => expect(useToast.getState().toasts.some((toast) => toast.message === 'Share link generation failed: Share signing unavailable')).toBe(true))
  expect((generate as HTMLButtonElement).disabled).toBe(false)
  expect(screen.queryByText(/\/view\/share\//)).toBeNull()
})

// The contract fixture is shared with the backend's real export producer checks.
import exportSchemas from '../../../../tests/contract/fixtures/export_schemas.json'

it('exports frame GeoJSON with the public property keys and excludes missing GPS', async () => {
  const parts: BlobPart[][] = []
  const NativeBlob = globalThis.Blob
  vi.stubGlobal('Blob', class extends NativeBlob {
    constructor(blobParts: BlobPart[] = [], options?: BlobPropertyBag) {
      super(blobParts, options)
      parts.push(blobParts)
    }
  })
  const NativeURL = globalThis.URL
  vi.stubGlobal('URL', class extends NativeURL {
    static createObjectURL = vi.fn(() => 'blob:frame-contract')
    static revokeObjectURL = vi.fn()
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  stubApi(({ method, url }) => {
    if (method === 'GET' && url === `/images?session_id=${SESSION_ID}`) {
      return jsonResponse([
        { filename: 'frame.jpg', latitude: 1, longitude: 2, altitude_m: null, flag: null, usable: null },
        { filename: 'no-gps.jpg', latitude: null, longitude: 2, altitude_m: null, flag: 'no_gps', usable: false },
      ])
    }
    return undefined
  })
  renderExportTab()
  await userEvent.click(await screen.findByRole('button', { name: 'Export GeoJSON' }))
  await waitFor(() => expect(parts).toHaveLength(1))
  const geojson = JSON.parse(String(parts[0][0]))
  expect(geojson.type).toBe('FeatureCollection')
  expect(geojson.features).toHaveLength(1)
  expect(geojson.features[0].geometry).toEqual({ type: 'Point', coordinates: [2, 1] })
  expect(Object.keys(geojson.features[0].properties).sort()).toEqual(exportSchemas.geojson.frames)
  expect(geojson.features[0].properties).toEqual({ filename: 'frame.jpg', altitude_m: null, flag: null, usable: null })
})
