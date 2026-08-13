// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import StorageTab from './StorageTab'
import { useToast } from '../../shared/hooks/useToast'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function renderStorageTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <StorageTab />
    </QueryClientProvider>,
  )
}

const storageSummary = {
  total_bytes: 0,
  by_type: { imports: 0, processed: 0, exports: 0, data: 0 },
  by_session: [],
}

const dryRunResult = {
  mode: 'dry-run' as const,
  candidates: [],
  summary: { total_items: 3, total_bytes: 1_200_000_000, actions: { delete: 3 } },
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useToast.setState({ toasts: [] })
})

describe('StorageTab lifecycle policy', () => {
  it('disables Execute when rules change after a dry run', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/storage/summary') return jsonResponse(storageSummary)
      if (url === '/storage/backup-schedule') return jsonResponse({ enabled: false })
      if (url === '/storage/files?directory=imports') return jsonResponse({ directory: 'imports', files: [] })
      if (url === '/storage/apply-policy' && init?.method === 'POST') return jsonResponse(dryRunResult)
      throw new Error(`Unexpected request: ${url}`)
    }))

    renderStorageTab()
    await screen.findByText('Lifecycle Policy')

    fireEvent.click(screen.getByRole('button', { name: 'Dry Run' }))
    const execute = screen.getByRole('button', { name: 'Execute' }) as HTMLButtonElement
    await waitFor(() => expect(execute.disabled).toBe(false))

    const ageInput = screen.getAllByRole('spinbutton').find((input) => !input.hasAttribute('disabled'))
    if (!(ageInput instanceof HTMLInputElement)) throw new Error('Age input not found')
    fireEvent.change(ageInput, { target: { value: '1' } })

    expect(execute.disabled).toBe(true)
  })
})
