import { useEffect, useRef } from 'react'
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet'
import type { LatLngBoundsExpression } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useMapStore } from '../../shared/stores/mapStore'
import { useFootprints } from '../map/hooks/useFootprints'
import type { Footprint } from '../../types/api'
import { comparisonViewportSource, shouldApplyComparisonViewport } from './comparisonViewport'
import { comparisonFootprintBounds, comparisonFootprintGeoJson } from './comparisonFootprints'

const ESRI_SATELLITE =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'

function SyncController({ reconstructionId }: { reconstructionId: number }) {
  const map = useMap()
  const { syncedViewport, setSyncedViewport } = useMapStore()
  const ignoreNextMoveRef = useRef(false)

  useEffect(() => {
    if (!syncedViewport || !shouldApplyComparisonViewport(syncedViewport.source, reconstructionId)) return
    ignoreNextMoveRef.current = true
    map.setView([syncedViewport.lat, syncedViewport.lon], syncedViewport.zoom, { animate: false })
  }, [syncedViewport, map, reconstructionId])

  useEffect(() => {
    function onMoveEnd() {
      if (ignoreNextMoveRef.current) {
        ignoreNextMoveRef.current = false
        return
      }
      const center = map.getCenter()
      setSyncedViewport({
        lat: center.lat,
        lon: center.lng,
        zoom: map.getZoom(),
        source: comparisonViewportSource(reconstructionId),
      })
    }
    map.on('moveend', onMoveEnd)
    return () => { map.off('moveend', onMoveEnd) }
  }, [map, reconstructionId, setSyncedViewport])

  return null
}

function InitialSessionBounds({ footprints }: { footprints: Footprint[] }) {
  const map = useMap()
  const syncedViewport = useMapStore((state) => state.syncedViewport)
  const fitted = useRef(false)

  useEffect(() => {
    if (fitted.current || syncedViewport) return
    const bounds = comparisonFootprintBounds(footprints)
    if (bounds.length > 0) {
      map.fitBounds(bounds as LatLngBoundsExpression, { padding: [12, 12] })
      fitted.current = true
    }
  }, [footprints, map, syncedViewport])

  return null
}

function SessionFootprints({ footprints }: { footprints: Footprint[] }) {
  const overlay = comparisonFootprintGeoJson(footprints)

  return overlay.features.length > 0 ? (
    <GeoJSON
      data={overlay}
      style={{ color: '#B87C4C', fillColor: '#B87C4C', fillOpacity: 0.16, weight: 1.5 }}
    />
  ) : null
}

export default function CompareMapPane({ reconstructionId, sessionId }: { reconstructionId: number; sessionId: number }) {
  const { data: footprints = [] } = useFootprints(sessionId)

  return (
    <MapContainer
      center={[35, -80]}
      zoom={15}
      style={{ width: '100%', height: 220 }}
      zoomControl={false}
      attributionControl={false}
    >
      <TileLayer url={ESRI_SATELLITE} attribution="© Esri" />
      <SyncController reconstructionId={reconstructionId} />
      <InitialSessionBounds footprints={footprints} />
      <SessionFootprints footprints={footprints} />
    </MapContainer>
  )
}
