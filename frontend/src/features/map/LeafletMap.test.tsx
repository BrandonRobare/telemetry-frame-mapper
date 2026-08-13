// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import LeafletMapView from './LeafletMap'
import { ErrorBoundary } from '../../ErrorBoundary'
import { useMapStore } from '../../shared/stores/mapStore'
import type { CoverageResult } from '../../types/api'

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  GeoJSON: () => <div data-testid="geojson" />,
  useMap: () => ({ fitBounds: vi.fn() }),
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
  useMapStore.setState({
    activeLayers: { footprints: true, coverage: true, heatmap: false, slope: false, targetArea: true },
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
