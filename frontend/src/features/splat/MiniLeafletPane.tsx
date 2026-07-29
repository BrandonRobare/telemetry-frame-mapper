import { useEffect, useRef } from 'react'
import { MapContainer, TileLayer, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { useMapStore } from '../../shared/stores/mapStore'

const ESRI_SATELLITE =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'

// Inner component so it can access the Leaflet map instance via useMap()
function SyncController() {
  const map = useMap()
  const { syncedViewport, setSyncedViewport } = useMapStore()
  const ignoreNextMoveRef = useRef(false)

  // When 3D camera moves, update this Leaflet map
  useEffect(() => {
    if (!syncedViewport || syncedViewport.source !== '3d') return
    ignoreNextMoveRef.current = true
    map.setView([syncedViewport.lat, syncedViewport.lon], syncedViewport.zoom, { animate: false })
  }, [syncedViewport, map])

  // When the Leaflet map moves, push to syncedViewport for the 3D camera
  useEffect(() => {
    function onMoveEnd() {
      if (ignoreNextMoveRef.current) {
        ignoreNextMoveRef.current = false
        return
      }
      const center = map.getCenter()
      setSyncedViewport({ lat: center.lat, lon: center.lng, zoom: map.getZoom(), source: 'leaflet' })
    }
    map.on('moveend', onMoveEnd)
    return () => { map.off('moveend', onMoveEnd) }
  }, [map, setSyncedViewport])

  return null
}

// Fallback only. Reached when a reconstruction has no solved geo-transform, in
// which case there is no site to centre on.
const FALLBACK_CENTER: [number, number] = [35.0, -80.0]

export default function MiniLeafletPane({ center }: { center?: [number, number] | null }) {
  return (
    <div style={{ width: '40%', height: '100%', borderRight: '1px solid var(--border)', flexShrink: 0 }}>
      <MapContainer
        // The pane only recentres once the 3D camera publishes a viewport, so
        // without this it opened on the fallback — satellite imagery hundreds of
        // kilometres from the reconstruction until the user happened to orbit.
        center={center ?? FALLBACK_CENTER}
        zoom={15}
        style={{ width: '100%', height: '100%' }}
        zoomControl={false}
        attributionControl={false}
      >
        <TileLayer url={ESRI_SATELLITE} attribution="© Esri" />
        <SyncController />
      </MapContainer>
    </div>
  )
}
