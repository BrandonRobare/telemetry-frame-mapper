import { useMapStore } from '../../shared/stores/mapStore'
import { useSession } from './hooks/useSession'
import { useFootprints } from './hooks/useFootprints'
import { useCoverageResult } from './hooks/useCoverageResult'
import LeafletMapView from './LeafletMap'
import LayerControls from './LayerControls'
import SessionSidebar from './SessionSidebar'

export default function MapTab() {
  const { selectedSessionId } = useMapStore()

  const { data: session } = useSession(selectedSessionId)
  const { data: footprints = [], isLoading, error } = useFootprints(selectedSessionId)
  const { data: coverage } = useCoverageResult(selectedSessionId)

  return (
    <div className="flex flex-1 overflow-hidden relative">
      {/* Map + floating controls */}
      <div className="relative flex-1">
        <LeafletMapView
          footprints={footprints}
          coverage={coverage ?? null}
          isLoading={isLoading}
          error={error as Error | null}
        />
        <LayerControls />
      </div>

      {/* Sidebar */}
      <SessionSidebar
        session={session}
        coverage={coverage}
        frameCount={footprints.length}
      />
    </div>
  )
}
