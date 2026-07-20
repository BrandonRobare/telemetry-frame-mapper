import { lazy, Suspense, useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useMapStore } from '../../shared/stores/mapStore'
import { useSession } from './hooks/useSession'
import { useFootprints } from './hooks/useFootprints'
import { useCoverageResult } from './hooks/useCoverageResult'
import { useSlopeOverlay } from './hooks/useSlopeOverlay'
import { isLiveImportStatus, useSessionProgress } from '../../shared/api/useSessionProgress'
import LeafletMapView from './LeafletMap'
import LayerControls from './LayerControls'
import SessionSidebar from './SessionSidebar'

// Code-split: three.js only ships when the no-session hero is shown.
const GlassHero3D = lazy(() => import('../hero/GlassHero3D'))

interface Props {
  onImport?: () => void
}

export default function MapTab({ onImport }: Props) {
  const { selectedSessionId, sidebarOpen, toggleSidebar, activeLayers } = useMapStore()
  const queryClient = useQueryClient()

  const { data: session } = useSession(selectedSessionId)
  const { data: importProgress } = useSessionProgress(selectedSessionId)
  const isImporting = isLiveImportStatus(importProgress?.status)
  const { data: footprints = [], isLoading, error } = useFootprints(selectedSessionId, {
    live: isImporting,
  })
  const { data: coverage } = useCoverageResult(selectedSessionId)
  const slopeOverlay = useSlopeOverlay(selectedSessionId, activeLayers.slope)

  // Once the live import settles (done/error), refetch once more so the map
  // reflects the authoritative final footprint/session state, then drop back
  // to the normal (non-polling) fetch policy.
  const wasImporting = useRef(false)
  useEffect(() => {
    if (wasImporting.current && !isImporting) {
      queryClient.invalidateQueries({ queryKey: ['footprints', selectedSessionId] })
      queryClient.invalidateQueries({ queryKey: ['session', selectedSessionId] })
    }
    wasImporting.current = isImporting
  }, [isImporting, selectedSessionId, queryClient])

  const sidebarWidth = sidebarOpen ? 200 : 20

  // No session yet → the 3D glass landing hero instead of an empty map.
  if (!selectedSessionId) {
    return (
      <Suspense fallback={<div className="tg-topo-backdrop flex-1" />}>
        <GlassHero3D onImport={onImport} />
      </Suspense>
    )
  }

  return (
    <div className="fm-map-layout flex flex-1 overflow-hidden relative">
      {/* Map + floating controls */}
      <div className="fm-map-canvas relative flex-1 flex flex-col">
        {isImporting && (
          <div
            className="absolute z-20 flex items-center gap-2 text-xs"
            style={{
              top: 12,
              left: 12,
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '6px 10px',
              color: 'var(--text)',
            }}
          >
            <span
              aria-hidden
              style={{
                width: 7, height: 7, borderRadius: '50%',
                background: 'var(--accent)',
                display: 'inline-block',
                animation: 'fm-pulse 1.2s var(--ease) infinite',
              }}
            />
            Importing…{' '}
            {importProgress && importProgress.total > 0
              ? `${importProgress.processed}/${importProgress.total} frames mapped`
              : `${footprints.length} frames mapped`}
          </div>
        )}
        <LeafletMapView
          footprints={footprints}
          coverage={coverage ?? null}
          slopeOverlay={slopeOverlay.data ?? null}
          isLoading={isLoading}
          error={error as Error | null}
        />
        <LayerControls slopeError={slopeOverlay.error instanceof Error ? slopeOverlay.error.message : undefined} />
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
        isLoading={isLoading}
      />
    </div>
  )
}
