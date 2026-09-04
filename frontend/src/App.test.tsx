// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { useMapStore } from './shared/stores/mapStore'

// Render counter for the mocked Overview tab — App re-rendering drags the
// whole active-tab subtree with it, so this doubles as an App render counter.
const counters = vi.hoisted(() => ({ overview: 0 }))

// A tab that blows up during render, the way a bare JSON.parse on bad
// persisted data does (#605). Without a per-tab boundary this takes the whole
// application down to the root boundary's full-viewport panel (#649).
vi.mock('./features/review/ReviewTab', () => ({
  default: () => {
    throw new Error('bad geometry in persisted state')
  },
}))

vi.mock('./features/overview/OverviewTab', () => ({
  default: () => {
    counters.overview++
    return <div>overview tab content</div>
  },
}))

const INLINE_ERROR = /This tab failed to render/

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderApp(tab: string) {
  vi.stubGlobal('fetch', vi.fn(async () =>
    new Response('[]', { status: 200, headers: { 'content-type': 'application/json' } }),
  ))
  window.history.replaceState(null, '', `/?tab=${tab}`)
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  )
}

describe('App per-tab error boundary', () => {
  it('keeps the shell alive when a tab throws during render', async () => {
    renderApp('review')

    // Tabs are lazy (#594), so the throw arrives once the chunk resolves —
    // the guarantee under test is unchanged, only its timing.
    await waitFor(() => expect(screen.getByText(INLINE_ERROR)).toBeTruthy())

    // The failing tab is reduced to an inline panel...
    expect(screen.getByText('bad geometry in persisted state')).toBeTruthy()

    // ...and the shell around it is still mounted and usable.
    expect(screen.getByRole('button', { name: /Telemetry Frame Mapper/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Overview' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '+ Import' })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Tools/ })).toBeTruthy()
  })

  it('clears the caught error when the operator switches tabs', async () => {
    renderApp('review')
    await waitFor(() => expect(screen.getByText(INLINE_ERROR)).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Overview' }))

    // A boundary that never resets would strand the operator on the dead panel.
    await waitFor(() => expect(screen.getByText('overview tab content')).toBeTruthy())
    expect(screen.queryByText(INLINE_ERROR)).toBeNull()
  })
})

describe('App store subscription', () => {
  // #664: `const { requestedTab } = useMapStore()` selects the whole state
  // object, which is a new reference after every `set`. Orbiting the splat
  // viewer calls setSyncedViewport at pointer-move rate, so the nav, the HUD
  // and the whole active tab reconciled on every frame of a drag.
  it('does not re-render on an unrelated store write', async () => {
    renderApp('overview')
    await waitFor(() => expect(screen.getByText('overview tab content')).toBeTruthy())

    const before = counters.overview
    act(() => {
      useMapStore.getState().setSyncedViewport({ lat: 47.6, lon: -122.3, zoom: 17, source: '3d' })
    })

    expect(counters.overview).toBe(before)
  })
})
