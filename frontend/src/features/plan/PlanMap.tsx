import { useEffect, useCallback } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet-draw/dist/leaflet.draw.css'
import 'leaflet-draw'

interface DrawControlProps {
  onPolygonDrawn: (geojsonStr: string) => void
}

function DrawControl({ onPolygonDrawn }: DrawControlProps) {
  const map = useMap()

  useEffect(() => {
    const drawnItems = new L.FeatureGroup()
    map.addLayer(drawnItems)

    // L.Control.Draw is augmented by @types/leaflet-draw
    const drawControl = new (L.Control as unknown as { Draw: new (opts: unknown) => L.Control }).Draw({
      edit: { featureGroup: drawnItems },
      draw: {
        polygon: { shapeOptions: { color: '#B87C4C', fillOpacity: 0.15 } },
        polyline: false,
        rectangle: false,
        circle: false,
        marker: false,
        circlemarker: false,
      },
    })
    map.addControl(drawControl)

    const handler = (e: L.LeafletEvent) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const layer = (e as any).layer as L.Layer
      drawnItems.clearLayers()
      drawnItems.addLayer(layer)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const geom = (layer as any).toGeoJSON().geometry
      onPolygonDrawn(JSON.stringify(geom))
    }

    map.on('draw:created', handler)

    return () => {
      map.off('draw:created', handler)
      map.removeControl(drawControl)
      map.removeLayer(drawnItems)
    }
  // onPolygonDrawn ref won't change — suppress exhaustive-deps
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map])

  return null
}

interface PlanMapProps {
  lanesGeoJSON: object | null
  onPolygonDrawn: (geojsonStr: string) => void
}

export default function PlanMap({ lanesGeoJSON, onPolygonDrawn }: PlanMapProps) {
  // Stable callback ref so DrawControl doesn't re-mount on parent re-renders
  const stableCallback = useCallback(onPolygonDrawn, [])  // eslint-disable-line

  return (
    <MapContainer
      center={[39.5, -98.35]}
      zoom={4}
      style={{ height: '100%', width: '100%' }}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="© OpenStreetMap contributors"
      />

      <DrawControl onPolygonDrawn={stableCallback} />

      {lanesGeoJSON && (
        <GeoJSON
          key={JSON.stringify(lanesGeoJSON).length}
          data={lanesGeoJSON as GeoJSON.GeoJsonObject}
          style={{ color: '#f0c040', weight: 2, fillOpacity: 0 }}
        />
      )}
    </MapContainer>
  )
}
