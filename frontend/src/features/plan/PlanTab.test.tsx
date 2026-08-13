// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PlanTab from './PlanTab'
import { ErrorBoundary } from '../../ErrorBoundary'
import { useToast } from '../../shared/hooks/useToast'

vi.mock('./PlanMap', () => ({
  default: ({
    lanesGeoJSON,
    onPolygonDrawn,
  }: {
    lanesGeoJSON: object | null
    onPolygonDrawn: (geojson: string) => void
  }) => (
    <>
      <button onClick={() => onPolygonDrawn('{"type":"Polygon","coordinates":[[[0,0],[1,0],[0,1],[0,0]]]}')}>Draw area</button>
      {lanesGeoJSON && <div data-testid="lanes-overlay" />}
    </>
  ),
}))

vi.mock('./WeatherAdvisorPanel', () => ({ default: () => null }))

const plan = {
  id: 42,
  target_area_id: 7,
  altitude_ft: 200,
  side_overlap_pct: 0.7,
  forward_overlap_pct: 0.8,
  lane_count: 6,
  total_distance_m: 6000,
  batteries_estimated: 2,
  lanes_geojson: null,
  kml_path: '/exports/plan_42.kml',
  gpx_path: '/exports/plan_42.gpx',
}

const segments = [
  {
    index: 0, from_lane: 0, to_lane: 2, distance_m: 3000,
    landing_wpt: null, resume_wpt: null, lanes_geojson: null,
    kml_path: '/exports/plan_42_seg_0.kml', gpx_path: '/exports/plan_42_seg_0.gpx',
  },
  {
    index: 1, from_lane: 3, to_lane: 5, distance_m: 3000,
    landing_wpt: null, resume_wpt: null, lanes_geojson: null,
    kml_path: '/exports/plan_42_seg_1.kml', gpx_path: '/exports/plan_42_seg_1.gpx',
  },
]

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function renderPlanTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <PlanTab />
      </QueryClientProvider>
    </ErrorBoundary>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useToast.setState({ toasts: [] })
})

describe('PlanTab malformed lane geometry', () => {
  it.each([
    '{not valid JSON',
    '{"type":"LineString","coordinates":[["not-a-number",null]]}',
  ])('skips an unrenderable lanes overlay without firing the root ErrorBoundary', async (lanesGeoJSON) => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/target-areas/')) return jsonResponse({ id: 7 })
      if (url.endsWith('/plans/generate')) {
        return jsonResponse({ ...plan, lanes_geojson: lanesGeoJSON })
      }
      throw new Error(`Unexpected request: ${url}`)
    }))
    renderPlanTab()

    fireEvent.click(screen.getByRole('button', { name: 'Draw area' }))
    await screen.findByText(/Target area saved/)
    fireEvent.click(screen.getByRole('button', { name: 'Generate Plan' }))

    expect(await screen.findByText('Plan Summary')).toBeTruthy()
    expect(screen.queryByText('Render error. Check console for details')).toBeNull()
    expect(screen.queryByTestId('lanes-overlay')).toBeNull()
  })
})

describe('PlanTab segment downloads', () => {
  it('opens each selected segment download endpoint rather than the whole plan', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/target-areas/')) return jsonResponse({ id: 7 })
      if (url.endsWith('/plans/generate')) return jsonResponse(plan)
      if (url.endsWith('/plans/42/segments')) return jsonResponse(segments)
      throw new Error(`Unexpected request: ${url}`)
    }))
    const open = vi.fn()
    vi.stubGlobal('open', open)
    renderPlanTab()

    fireEvent.click(screen.getByRole('button', { name: 'Draw area' }))
    await screen.findByText(/Target area saved/)
    fireEvent.click(screen.getByRole('button', { name: 'Generate Plan' }))
    await screen.findByText('Plan Summary')
    fireEvent.click(screen.getByRole('button', { name: 'Segments' }))
    await screen.findByText('Battery Segments (2)')

    const kmlButtons = screen.getAllByRole('button', { name: 'KML ↓' })
    const gpxButtons = screen.getAllByRole('button', { name: 'GPX ↓' })
    fireEvent.click(kmlButtons[1])
    fireEvent.click(gpxButtons[2])

    await waitFor(() => {
      expect(open).toHaveBeenCalledWith('/plans/42/segments/0/kml', '_blank')
      expect(open).toHaveBeenCalledWith('/plans/42/segments/1/gpx', '_blank')
    })
  })
})
