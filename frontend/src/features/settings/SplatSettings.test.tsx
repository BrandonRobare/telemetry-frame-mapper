// @vitest-environment jsdom
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import SplatSettings from './SplatSettings'
import { settingsFixture } from '../../test/settings'

// #820: Metal's `quick` preset runs at 1,250 iterations by accelerator policy
// (CUDA stays at 1,000) whenever config.yaml omits the field. GET /settings
// now reports that resolved value instead of the bare cross-platform default.

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function renderSplatSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <SplatSettings />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('SplatSettings save payload', () => {
  it('sends only the preset field the operator touched, not the untouched Metal-policy iterations', async () => {
    let patchBody: unknown = null
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url === '/settings' && (!init || init.method === undefined)) {
          return jsonResponse(settingsFixture)
        }
        if (url === '/settings' && init?.method === 'PATCH') {
          patchBody = JSON.parse(String(init.body))
          return jsonResponse(settingsFixture)
        }
        throw new Error(`Unexpected request: ${url} ${init?.method ?? 'GET'}`)
      }),
    )

    renderSplatSettings()

    // Open the `quick` preset's Advanced section (its own toggle is first in
    // document order) and edit max_gaussians only — `quick.iterations`
    // (1,250, the Metal-policy-derived value) is never touched.
    await screen.findByText('quick preset')
    await userEvent.click(screen.getAllByRole('button', { name: 'Advanced' })[0])
    const maxGaussiansInput = await screen.findByDisplayValue('350000')
    await userEvent.clear(maxGaussiansInput)
    await userEvent.type(maxGaussiansInput, '400000')

    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(patchBody).not.toBeNull())
    expect(patchBody).toEqual({
      reconstruction: { presets: { quick: { max_gaussians: 400000 } } },
    })
  })
})
