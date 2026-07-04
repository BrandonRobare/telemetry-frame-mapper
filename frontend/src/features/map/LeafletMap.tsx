import { useEffect, useRef } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet'
import type { LatLngBoundsExpression, Layer } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { Footprint, CoverageResult } from '../../types/api'
import { useMapStore } from '../../shared/stores/mapStore'

const BASEMAPS = {
  esri_satellite: {
    label: 'Esri Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: '© Esri',
  },
  osm: {
    label: 'OpenStreetMap',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '© OpenStreetMap contributors',
  },
  offline_mbtiles: {
    label: 'Offline tiles',
    url: '/tiles/{z}/{x}/{y}.png',
    attribution: 'Local offline tiles',
  },
} as const

// Leaflet sets these as SVG presentation attributes, so they must be literal
// hex (CSS vars don't resolve there). Kept in sync with the warm-light tokens:
// --accent (terracotta) and --sage.
const FOOTPRINT_COLOR = '#B87C4C'
const COVERAGE_COLOR = '#A8BBA3'

interface Props {
  footprints: Footprint[]
  coverage: CoverageResult | null
  isLoading: boolean
  error: Error | null
}

function FitBounds({ footprints }: { footprints: Footprint[] }) {
  const map = useMap()
  const fitted = useRef(false)
  const previousFootprints = useRef<Footprint[]>(footprints)

  useEffect(() => {
    if (previousFootprints.current !== footprints) {
      fitted.current = false
      previousFootprints.current = footprints
    }
    if (fitted.current || footprints.length === 0) return
    const coords: number[][] = []
    footprints.forEach((fp) => {
      try {
        const geom = JSON.parse(fp.geom_geojson)
        if (geom.coordinates) {
          const flat = (geom.coordinates as number[][][]).flat(2)
          for (let i = 0; i < flat.length; i += 2) coords.push([flat[i + 1], flat[i]])
        }
      } catch {
        // skip malformed footprints
      }
    })
    if (coords.length > 0) {
      map.fitBounds(coords as LatLngBoundsExpression, { padding: [20, 20] })
      fitted.current = true
    }
  }, [footprints, map])

  return null
}

export default function LeafletMapView({ footprints, coverage, isLoading, error }: Props) {
  const { activeLayers, basemapId, setBasemapId } = useMapStore()
  const basemap = BASEMAPS[basemapId as keyof typeof BASEMAPS] ?? BASEMAPS.esri_satellite

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div
          className="px-4 py-3 text-sm"
          style={{
            background: 'var(--danger-soft)',
            border: '1px solid var(--danger-accent)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--danger)',
          }}
        >
          Couldn't load the map. Check that the backend is running, then reload.
        </div>
      </div>
    )
  }

  function onEachFootprint(_feature: unknown, layer: Layer) {
    layer.on('click', () => {
      const { selectedSessionId, setTargetSessionId, setRequestedTab } = useMapStore.getState()
      if (selectedSessionId == null) return
      setTargetSessionId(selectedSessionId)
      setRequestedTab('splat')
    })
  }

  const footprintGeoJSON = footprints.length > 0
    ? {
        type: 'FeatureCollection' as const,
        features: footprints.reduce<
          { type: 'Feature'; geometry: unknown; properties: { id: number } }[]
        >((acc, fp) => {
          if (!fp.geom_geojson) return acc
          try {
            acc.push({
              type: 'Feature',
              geometry: JSON.parse(fp.geom_geojson),
              properties: { id: fp.id },
            })
          } catch {
            // skip malformed footprints
          }
          return acc
        }, []),
      }
    : null

  const gapGeoJSON = coverage?.gap_geojson ? JSON.parse(coverage.gap_geojson) : null

  return (
    <div className="relative w-full h-full">
      <label
        className="absolute z-20 flex items-center gap-2 text-xs"
        style={{
          top: 12,
          right: 12,
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          padding: '6px 8px',
          color: 'var(--text)',
        }}
      >
        Basemap
        <select
          value={basemapId}
          onChange={(event) => setBasemapId(event.target.value)}
          style={{
            background: 'var(--bg)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
          }}
        >
          {Object.entries(BASEMAPS).map(([id, provider]) => (
            <option key={id} value={id}>{provider.label}</option>
          ))}
        </select>
      </label>

      {basemapId === 'offline_mbtiles' && (
        <div
          className="absolute z-20 text-xs"
          style={{
            top: 54,
            right: 12,
            background: 'var(--surface)',
            border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-sm)',
            padding: '6px 8px',
            color: 'var(--text-muted)',
          }}
        >
          Offline mode expects local tiles at /tiles/{'{z}'}/{'{x}'}/{'{y}'}.png.
        </div>
      )}

      {isLoading && (
        <div
          className="absolute inset-0 z-10 flex items-center justify-center"
          style={{ background: 'var(--bg)', opacity: 0.7 }}
        >
          <span style={{ color: 'var(--text-muted)' }}>Loading map data…</span>
        </div>
      )}

      <MapContainer
        center={[39.5, -98.35]}
        zoom={4}
        style={{ height: '100%', width: '100%' }}
      >
        <TileLayer
          url={basemap.url}
          attribution={basemap.attribution}
        />

        {activeLayers.footprints && footprintGeoJSON && (
          <GeoJSON
            key={JSON.stringify(footprintGeoJSON).length}
            data={footprintGeoJSON}
            style={{
              color: FOOTPRINT_COLOR,
              fillColor: FOOTPRINT_COLOR,
              fillOpacity: 0.13,
              weight: 1.5,
            }}
            onEachFeature={onEachFootprint}
          />
        )}

        {activeLayers.coverage && gapGeoJSON && (
          <GeoJSON
            key={`cov-${coverage?.id}`}
            data={gapGeoJSON}
            style={{
              color: COVERAGE_COLOR,
              fillColor: COVERAGE_COLOR,
              fillOpacity: 0.12,
              weight: 1.5,
            }}
          />
        )}

        <FitBounds footprints={activeLayers.footprints ? footprints : []} />
      </MapContainer>
    </div>
  )
}
