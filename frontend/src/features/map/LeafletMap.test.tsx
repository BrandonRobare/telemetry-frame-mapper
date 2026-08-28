// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import LeafletMapView from './LeafletMap'
import { ErrorBoundary } from '../../ErrorBoundary'
import { useMapStore } from '../../shared/stores/mapStore'
import type { CoverageResult, Footprint } from '../../types/api'

const { fitBounds } = vi.hoisted(() => ({ fitBounds: vi.fn() }))

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  GeoJSON: () => <div data-testid="geojson" />,
  useMap: () => ({ fitBounds }),
}))

const coverage: CoverageResult = {
  id: 1,
  target_area_id: 7,
  session_ids: '1',
  total_area_m2: 100,
  covered_area_m2: 75,
  coverage_pct: 75,
  gap_geojson: '{not valid JSON',
  overlap_geojson: null,
  run_at: '2026-08-12T00:00:00Z',
}

afterEach(() => {
  cleanup()
  fitBounds.mockClear()
  useMapStore.setState({
    selectedSessionId: null,
    activeLayers: { footprints: true, coverage: true, slope: false },
  })
})

describe('LeafletMap malformed coverage geometry', () => {
  it.each([
    '{not valid JSON',
    '{"type":"Point","coordinates":["not-a-number",null]}',
  ])('skips an unrenderable coverage-gap overlay without firing the root ErrorBoundary', (gapGeoJSON) => {
    render(
      <ErrorBoundary>
        <LeafletMapView
          footprints={[]}
          coverage={{ ...coverage, gap_geojson: gapGeoJSON }}
          slopeOverlay={null}
          isLoading={false}
          error={null}
        />
      </ErrorBoundary>,
    )

    expect(screen.getByTestId('map')).toBeTruthy()
    expect(screen.queryByText('Render error. Check console for details')).toBeNull()
    expect(screen.queryByTestId('geojson')).toBeNull()
  })
})

function footprint(id: number, lon: number): Footprint {
  return {
    id,
    image_id: id,
    geom_wkt: '',
    geom_geojson: JSON.stringify({
      type: 'Polygon',
      coordinates: [[[lon, 0], [lon + 1, 0], [lon + 1, 1], [lon, 1], [lon, 0]]],
    }),
    ground_width_m: 10,
    ground_height_m: 10,
    heading_estimated: false,
  }
}

function mapView(footprints: Footprint[]) {
  return (
    <LeafletMapView
      footprints={footprints}
      coverage={null}
      slopeOverlay={null}
      isLoading={false}
      error={null}
    />
  )
}

describe('LeafletMap auto-fit', () => {
  it('does not re-fit when a live poll appends another page of footprints', () => {
    useMapStore.setState({ selectedSessionId: 1 })
    const { rerender } = render(mapView([footprint(1, 0)]))
    expect(fitBounds).toHaveBeenCalledTimes(1)

    // mergeFootprintPage returns a brand-new array for every non-empty poll
    // page, so the map sees a fresh identity roughly every 1.5s during an
    // import. Re-fitting on those would yank the view away from an operator
    // who has panned or zoomed (#662).
    rerender(mapView([footprint(1, 0), footprint(2, 2)]))
    rerender(mapView([footprint(1, 0), footprint(2, 2), footprint(3, 4)]))

    expect(fitBounds).toHaveBeenCalledTimes(1)
  })

  it('fits again when a different session is selected', () => {
    useMapStore.setState({ selectedSessionId: 1 })
    const { rerender } = render(mapView([footprint(1, 0)]))
    expect(fitBounds).toHaveBeenCalledTimes(1)

    // Switching sessions changes the react-query key, so the new session's
    // footprints start out empty before its first page lands.
    act(() => {
      useMapStore.setState({ selectedSessionId: 2 })
    })
    rerender(mapView([]))
    rerender(mapView([footprint(9, 40)]))

    expect(fitBounds).toHaveBeenCalledTimes(2)
  })
})
