// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ShareViewer from './ShareViewer'

const TOKEN = 'tfm_share_token'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

/** Answers the viewer's metadata request with `response`. */
function stubMetadata(response: () => Response) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url === `/share/token/${TOKEN}` && !init?.method) return response()
    throw new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url}`)
  }))
}

function renderViewer() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ShareViewer />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  window.history.pushState({}, '', `/view/share/${TOKEN}`)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.history.pushState({}, '', '/')
})

describe('ShareViewer password prompt', () => {
  it('shows the password form for a 401 with code share_password_required', async () => {
    stubMetadata(() => jsonResponse(401, {
      detail: 'This text is for people and may change',
      code: 'share_password_required',
    }))
    renderViewer()

    expect(await screen.findByRole('heading', { name: 'Password-protected share' })).toBeTruthy()
    expect(screen.getByLabelText('Password')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Unlock' })).toBeTruthy()
  })

  it('does not treat the message text alone as a password prompt', async () => {
    stubMetadata(() => jsonResponse(401, { detail: 'Share link password required' }))
    renderViewer()

    expect(await screen.findByText('Share link password required')).toBeTruthy()
    expect(screen.getByText('401')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Unlock' })).toBeNull()
  })

  it('shows a revoked link as gone with the status the backend sent', async () => {
    stubMetadata(() => jsonResponse(410, { detail: 'Share link has expired or been revoked' }))
    renderViewer()

    expect(await screen.findByText('Share link has expired or been revoked')).toBeTruthy()
    expect(screen.getByText('410')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Unlock' })).toBeNull()
  })
})
