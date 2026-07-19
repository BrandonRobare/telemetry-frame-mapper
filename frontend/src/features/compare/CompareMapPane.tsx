import { useEffect, useRef } from 'react'
import { MapContainer, TileLayer, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { useMapStore } from '../../shared/stores/mapStore'
import { comparisonViewportSource, shouldApplyComparisonViewport } from './comparisonViewport'

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

export default function CompareMapPane({ reconstructionId }: { reconstructionId: number }) {
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
    </MapContainer>
  )
}
