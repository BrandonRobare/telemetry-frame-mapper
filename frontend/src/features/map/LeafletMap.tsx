import { useEffect, useRef } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet'
import type { Map as LeafletMap, LatLngBoundsExpression } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { Footprint, CoverageResult } from '../../types/api'
import { useMapStore } from '../../shared/stores/mapStore'

const ESRI_SATELLITE =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
const OSM = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'

interface Props {
  footprints: Footprint[]
  coverage: CoverageResult | null
  isLoading: boolean
  error: Error | null
}

function FitBounds({ footprints }: { footprints: Footprint[] }) {
  const map = useMap()
  const fitted = useRef(false)

  useEffect(() => {
    if (fitted.current || footprints.length === 0) return
    const coords: number[][] = []
    footprints.forEach((fp) => {
      try {
        const geom = JSON.parse(fp.geom_geojson)
        if (geom.coordinates) {
          const flat = (geom.coordinates as number[][][]).flat(2)
          for (let i = 0; i < flat.length; i += 2) coords.push([flat[i + 1], flat[i]])
        }
      } catch { /* skip malformed */ }
    })
    if (coords.length > 0) {
      map.fitBounds(coords as LatLngBoundsExpression, { padding: [20, 20] })
      fitted.current = true
    }
  }, [footprints, map])

  return null
}

export default function LeafletMapView({ footprints, coverage, isLoading, error }: Props) {
  const { activeLayers } = useMapStore()
  const mapRef = useRef<LeafletMap | null>(null)

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div
          className="rounded px-4 py-3 text-sm"
          style={{ background: '#3b000022', border: '1px solid var(--danger)', color: 'var(--danger)' }}
        >
          Could not load footprints — is the backend running?
        </div>
      </div>
    )
  }

  const footprintGeoJSON = footprints.length > 0
    ? { type: 'FeatureCollection' as const, features: footprints.map((fp) => ({ type: 'Feature' as const, geometry: JSON.parse(fp.geom_geojson), properties: { id: fp.id } })) }
    : null

  const gapGeoJSON = coverage?.gap_geojson ? JSON.parse(coverage.gap_geojson) : null

  return (
    <div className="relative flex-1">
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
        ref={mapRef}
      >
        <TileLayer
          url={activeLayers.footprints ? ESRI_SATELLITE : OSM}
          attribution="© Esri"
        />

        {activeLayers.footprints && footprintGeoJSON && (
          <GeoJSON
            key={JSON.stringify(footprintGeoJSON).length}
            data={footprintGeoJSON}
            style={{ color: '#58a6ff', fillColor: '#58a6ff', fillOpacity: 0.13, weight: 1.5 }}
          />
        )}

        {activeLayers.coverage && gapGeoJSON && (
          <GeoJSON
            key={`cov-${coverage?.id}`}
            data={gapGeoJSON}
            style={{ color: '#4ade80', fillColor: '#4ade80', fillOpacity: 0.1, weight: 1.5 }}
          />
        )}

        <FitBounds footprints={activeLayers.footprints ? footprints : []} />
      </MapContainer>
    </div>
  )
}
