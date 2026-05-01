import { useMapStore } from '../../shared/stores/mapStore'
import { useSession } from './hooks/useSession'
import { useFootprints } from './hooks/useFootprints'
import { useCoverageResult } from './hooks/useCoverageResult'
import LeafletMapView from './LeafletMap'
import LayerControls from './LayerControls'
import SessionSidebar from './SessionSidebar'

export default function MapTab() {
  const { selectedSessionId, sidebarOpen, toggleSidebar } = useMapStore()

  const { data: session } = useSession(selectedSessionId)
  const { data: footprints = [], isLoading, error } = useFootprints(selectedSessionId)
  const { data: coverage } = useCoverageResult(selectedSessionId)

  const sidebarWidth = sidebarOpen ? 200 : 20

  return (
    <div className="flex flex-1 overflow-hidden relative">
      {/* Map + floating controls */}
      <div className="relative flex-1 flex flex-col">
        <LeafletMapView
          footprints={footprints}
          coverage={coverage ?? null}
          isLoading={isLoading}
          error={error as Error | null}
        />
        <LayerControls />
      </div>

      {/* Collapse / expand tab — sibling of aside so overflow-y-auto can't clip it */}
      {sidebarOpen && (
        <button
          onClick={toggleSidebar}
          title="Collapse sidebar"
          style={{
            position: 'absolute', right: sidebarWidth, top: '50%',
            transform: 'translateY(-50%)', zIndex: 500,
            width: 14, height: 36, cursor: 'pointer',
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRight: 'none', borderRadius: '4px 0 0 4px',
            color: 'var(--text-muted)', fontSize: 12,
          }}
        >›</button>
      )}

      {/* Sidebar */}
      <SessionSidebar
        session={session}
        coverage={coverage}
        frameCount={footprints.length}
      />
    </div>
  )
}
