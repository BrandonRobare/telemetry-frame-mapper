import { useState, type CSSProperties } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post } from '../../shared/api/client'
import { useMapStore } from '../../shared/stores/mapStore'
import { useToast } from '../../shared/hooks/useToast'
import { Button } from '../../shared/components/Button'
import TabHeader from '../../shared/components/TabHeader'
import EmptyState from '../../shared/components/EmptyState'
import type { Session, Image, Job, MeshStatus } from '../../types/api'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// ---- inline hooks ----

function useSession(sessionId: number | null) {
  return useQuery<Session>({
    queryKey: ['session', sessionId],
    queryFn: () => get<Session>(`/sessions/${sessionId}`),
    enabled: sessionId !== null,
  })
}

function useImages(sessionId: number | null) {
  return useQuery<Image[]>({
    queryKey: ['images', sessionId],
    queryFn: () => get<Image[]>(`/images?session_id=${sessionId}`),
    enabled: false, // only fetch on demand
  })
}

function useCompletedReconstructions(sessionId: number | null) {
  return useQuery<Job[]>({
    queryKey: ['jobs', 'export', sessionId],
    queryFn: () => get<Job[]>('/jobs/'),
    select: (jobs) => jobs.filter((job) => job.session_id === sessionId && job.status === 'complete'),
    enabled: sessionId !== null,
  })
}

function useMeshStatus(reconstructionId: number) {
  return useQuery<MeshStatus>({
    queryKey: ['mesh-status', reconstructionId],
    queryFn: () => get<MeshStatus>(`/reconstruction/${reconstructionId}/mesh/status`),
    refetchInterval: (query) => {
      const status = query.state.data?.mesh_status
      return status === 'pending' || status === 'running' ? 2000 : false
    },
  })
}

// ---- helpers ----

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return iso
  }
}

function MeshExportCard({ job }: { job: Job }) {
  const { addToast } = useToast()
  const qc = useQueryClient()
  const { data: mesh } = useMeshStatus(job.id)

  const meshMutation = useMutation({
    mutationFn: () => post<MeshStatus>(`/reconstruction/${job.id}/mesh`),
    onSuccess: () => {
      addToast(`Mesh export started for reconstruction #${job.id}`, 'success')
      qc.invalidateQueries({ queryKey: ['mesh-status', job.id] })
    },
    onError: (err: Error) => addToast(`Mesh export failed: ${err.message}`, 'error'),
  })

  const status = mesh?.mesh_status ?? null
  const running = status === 'pending' || status === 'running'
  const complete = status === 'complete'

  return (
    <div
      className="py-3 flex flex-col gap-3"
      style={{ borderBottom: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-3">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="text-sm" style={{ color: 'var(--text)', fontWeight: 600 }}>
            Reconstruction #{job.id}
          </div>
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {job.preset} · {job.frames_used} frames
          </div>
        </div>
        {!complete && (
          <Button
            variant="ghost"
            disabled={running || meshMutation.isPending}
            onClick={() => meshMutation.mutate()}
          >
            {running || meshMutation.isPending ? 'Generating…' : 'Generate Mesh'}
          </Button>
        )}
      </div>

      {running && (
        <div style={{ height: 5, background: 'var(--surface-2)', borderRadius: 3, overflow: 'hidden' }}>
          {/* Mesh export reports no percentage — show an indeterminate bar. */}
          <div
            className="tg-indeterminate"
            style={{
              height: '100%',
              width: '40%',
              background: 'var(--accent)',
              borderRadius: 3,
            }}
          />
        </div>
      )}

      {status === 'failed' && mesh?.mesh_error && (
        <p className="text-xs" style={{ color: 'var(--danger, #f85149)', margin: 0 }}>
          {mesh.mesh_error}
        </p>
      )}

      {complete && (
        <div className="flex gap-2 flex-wrap">
          {mesh?.mesh_glb_path && (
            <a
              href={`${BASE_URL}/reconstruction/${job.id}/mesh?format=glb`}
              download={`mesh_${job.id}.glb`}
              style={downloadLinkStyle}
            >
              Download GLB
            </a>
          )}
          {mesh?.mesh_obj_path && (
            <a
              href={`${BASE_URL}/reconstruction/${job.id}/mesh?format=obj`}
              download={`mesh_${job.id}.obj`}
              style={downloadLinkStyle}
            >
              Download OBJ
            </a>
          )}
          {mesh?.mesh_mtl_path && (
            <a
              href={`${BASE_URL}/reconstruction/${job.id}/mesh?format=mtl`}
              download={`mesh_${job.id}.mtl`}
              style={downloadLinkStyle}
            >
              Download MTL
            </a>
          )}
        </div>
      )}
    </div>
  )
}

const downloadLinkStyle: CSSProperties = {
  padding: '5px 10px',
  borderRadius: 'var(--radius-sm)',
  fontSize: 12,
  background: 'var(--accent-soft)',
  border: '1px solid var(--accent-soft)',
  color: 'var(--accent-strong)',
  textDecoration: 'none',
  whiteSpace: 'nowrap',
}

// ---- main component ----

export default function ExportTab() {
  const { selectedSessionId, setRequestedTab } = useMapStore()
  const { addToast } = useToast()

  const { data: session, isLoading: sessionLoading } = useSession(selectedSessionId)
  const { data: completedReconstructions, isLoading: reconstructionsLoading } =
    useCompletedReconstructions(selectedSessionId)

  // WebODM georeferencing CSV-only export state
  const [webodmResult, setWebodmResult] = useState<{
    session_id: number | null
    zip_path: string
    image_count: number
  } | null>(null)
  const visibleWebodmResult =
    webodmResult?.session_id === selectedSessionId ? webodmResult : null

  const webodmMutation = useMutation({
    mutationFn: () =>
      post<{ zip_path: string; image_count: number }>(
        `/export/webodm-georeferencing-csv?session_id=${selectedSessionId}`
      ),
    onSuccess: (data) => {
      setWebodmResult({ ...data, session_id: selectedSessionId })
    },
    onError: (err: Error) => {
      setWebodmResult(null)
      addToast(`WebODM georeferencing CSV export failed: ${err.message}`, 'error')
    },
  })

  // GeoJSON export — fetches images on demand then triggers browser download
  const { refetch: fetchImages, isFetching: imagesFetching } = useImages(selectedSessionId)

  async function handleGeoJsonExport() {
    const result = await fetchImages()
    const images = result.data ?? []

    const gpsImages = images.filter(
      (img) => img.latitude !== null && img.longitude !== null
    )

    if (gpsImages.length === 0) {
      addToast('No GPS images to export', 'info')
      return
    }

    const geojson = {
      type: 'FeatureCollection' as const,
      features: gpsImages.map((img) => ({
        type: 'Feature' as const,
        geometry: {
          type: 'Point' as const,
          coordinates: [img.longitude as number, img.latitude as number],
        },
        properties: {
          filename: img.filename,
          altitude_m: img.altitude_m,
          flag: img.flag,
          usable: img.usable,
        },
      })),
    }

    const blob = new Blob([JSON.stringify(geojson, null, 2)], {
      type: 'application/geo+json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `session_${selectedSessionId}_frames.geojson`
    a.click()
    URL.revokeObjectURL(url)

    addToast(`GeoJSON downloaded: ${gpsImages.length} features`, 'success')
  }

  // ---- guard: no session selected ----
  if (selectedSessionId === null) {
    return (
      <EmptyState
        title="No session selected"
        description="Choose a session to export its orthophoto, point cloud, mesh, or flythrough."
        actionLabel="Open Overview"
        onAction={() => setRequestedTab('overview')}
      />
    )
  }

  // ---- guard: loading session ----
  if (sessionLoading) {
    return (
      <div
        className="flex-1 flex items-center justify-center"
        style={{ color: 'var(--text-muted)' }}
      >
        Loading session…
      </div>
    )
  }

  // ---- zip filename helper ----
  const zipFilename = visibleWebodmResult
    ? (visibleWebodmResult.zip_path.split('/').pop() ?? visibleWebodmResult.zip_path)
    : null


  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <TabHeader
        title="Export"
        description="Download orthophotos, point clouds, meshes, and flythroughs."
      />
      <div
        className="flex-1 overflow-y-auto p-6"
        style={{ color: 'var(--text)' }}
      >
      <div
        className="mx-auto flex flex-col gap-6"
        style={{ maxWidth: 720 }}
      >
        {/* ---- Session summary card ---- */}
        <section
          className="p-5 flex flex-col gap-3"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <h2
            className="text-base font-semibold"
            style={{ color: 'var(--text)', margin: 0 }}
          >
            Session Summary
          </h2>

          {session && (
            <dl
              className="grid gap-x-8 gap-y-2 text-sm"
              style={{ gridTemplateColumns: 'auto 1fr' }}
            >
              <dt style={{ color: 'var(--text-muted)' }}>Name</dt>
              <dd style={{ color: 'var(--text)', margin: 0 }}>{session.name}</dd>

              <dt style={{ color: 'var(--text-muted)' }}>Total frames</dt>
              <dd style={{ color: 'var(--text)', margin: 0 }}>{session.photo_count}</dd>

              <dt style={{ color: 'var(--text-muted)' }}>Usable frames</dt>
              <dd style={{ color: 'var(--text)', margin: 0 }}>{session.usable_count}</dd>

              <dt style={{ color: 'var(--text-muted)' }}>Imported</dt>
              <dd style={{ color: 'var(--text)', margin: 0 }}>{formatDate(session.imported_at)}</dd>

              <dt style={{ color: 'var(--text-muted)' }}>Coverage</dt>
              <dd style={{ color: 'var(--text-muted)', margin: 0 }}>N/A</dd>
            </dl>
          )}
        </section>

        {/* ---- WebODM georeferencing CSV-only export card ---- */}
        <section
          className="p-5 flex flex-col gap-4"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <div>
            <h2
              className="text-base font-semibold"
              style={{ color: 'var(--text)', margin: 0 }}
            >
              WebODM georeferencing CSV
            </h2>
            <p
              className="text-sm mt-1"
              style={{ color: 'var(--text-muted)', margin: '4px 0 0' }}
            >
              Build a zip containing only odm_georeferencing.csv for WebODM/OpenDroneMap.
            </p>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <Button
              variant="primary"
              disabled={webodmMutation.isPending}
              onClick={() => {
                setWebodmResult(null)
                webodmMutation.mutate()
              }}
            >
              {webodmMutation.isPending ? 'Building…' : 'Download georeferencing CSV zip'}
            </Button>

            {visibleWebodmResult && (
              <div
                className="px-3 py-2 text-sm flex flex-col gap-0.5"
                style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
              >
                <span style={{ color: 'var(--success)', fontWeight: 600 }}>
                  Ready: {visibleWebodmResult.image_count} images
                </span>
                <span
                  className="font-mono text-xs"
                  style={{ color: 'var(--text-muted)', wordBreak: 'break-all' }}
                >
                  {zipFilename}
                </span>
              </div>
            )}
          </div>
        </section>

        {/* ---- GeoJSON Export card ---- */}
        <section
          className="p-5 flex flex-col gap-4"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <div>
            <h2
              className="text-base font-semibold"
              style={{ color: 'var(--text)', margin: 0 }}
            >
              GeoJSON Export
            </h2>
            <p
              className="text-sm mt-1"
              style={{ color: 'var(--text-muted)', margin: '4px 0 0' }}
            >
              Download frame positions as a GeoJSON FeatureCollection (Point per frame).
            </p>
          </div>

          <Button
            variant="ghost"
            disabled={imagesFetching}
            onClick={handleGeoJsonExport}
            style={{ alignSelf: 'flex-start' }}
          >
            {imagesFetching ? 'Fetching images…' : 'Export GeoJSON'}
          </Button>
        </section>

        {/* ---- Geometry Export card ---- */}
        <section
          className="rounded-lg p-5 flex flex-col gap-4"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <div>
            <h2
              className="text-base font-semibold"
              style={{ color: 'var(--text)', margin: 0 }}
            >
              Footprint & Coverage Geometry
            </h2>
            <p
              className="text-sm mt-1"
              style={{ color: 'var(--text-muted)', margin: '4px 0 0' }}
            >
              Download footprint polygons and latest coverage gaps/overlaps for QGIS or Google Earth.
            </p>
          </div>

          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm" style={{ color: 'var(--text)', minWidth: 82 }}>
                Footprints
              </span>
              {(['geojson', 'kml', 'kmz'] as const).map((format) => (
                <a
                  key={format}
                  href={`${BASE_URL}/footprints/export?session_id=${selectedSessionId}&format=${format}`}
                  download={`session_${selectedSessionId}_footprints.${format}`}
                  style={downloadLinkStyle}
                >
                  {format.toUpperCase()} ↓
                </a>
              ))}
            </div>

            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm" style={{ color: 'var(--text)', minWidth: 82 }}>
                Coverage
              </span>
              {(['geojson', 'kml', 'kmz'] as const).map((format) => (
                <a
                  key={format}
                  href={`${BASE_URL}/coverage/results/export?session_id=${selectedSessionId}&format=${format}`}
                  download={`session_${selectedSessionId}_coverage.${format}`}
                  style={downloadLinkStyle}
                >
                  {format.toUpperCase()} ↓
                </a>
              ))}
            </div>
          </div>
        </section>

        {/* ---- Point Cloud Export card ---- */}
        <section
          className="p-5 flex flex-col gap-4"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <div>
            <h2
              className="text-base font-semibold"
              style={{ color: 'var(--text)', margin: 0 }}
            >
              Point Cloud Export
            </h2>
            <p
              className="text-sm mt-1"
              style={{ color: 'var(--text-muted)', margin: '4px 0 0' }}
            >
              Download completed reconstructions as coloured LAS point clouds.
            </p>
          </div>

          {reconstructionsLoading && (
            <p className="text-sm" style={{ color: 'var(--text-muted)', margin: 0 }}>
              Loading reconstructions…
            </p>
          )}

          {!reconstructionsLoading && (completedReconstructions ?? []).length === 0 && (
            <p className="text-sm" style={{ color: 'var(--text-muted)', margin: 0 }}>
              No completed reconstruction is ready for point cloud export.
            </p>
          )}

          {(completedReconstructions ?? []).length > 0 && (
          <div style={{ borderTop: '1px solid var(--border)' }}>
          {(completedReconstructions ?? []).map((job, idx, arr) => (
            <div
              key={job.id}
              className="py-2.5 flex items-center gap-3"
              style={{ borderBottom: idx < arr.length - 1 ? '1px solid var(--border)' : 'none' }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="text-sm" style={{ color: 'var(--text)', fontWeight: 600 }}>
                  Reconstruction #{job.id}
                </div>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {job.preset} · {job.frames_used} frames
                </div>
              </div>
              <a
                href={`${BASE_URL}/reconstruction/${job.id}/pointcloud`}
                download={`pointcloud_${job.id}.las`}
                style={{
                  padding: '5px 10px',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 12,
                  background: 'var(--accent-soft)',
                  border: '1px solid var(--accent-soft)',
                  color: 'var(--accent-strong)',
                  textDecoration: 'none',
                  whiteSpace: 'nowrap',
                }}
              >
                Download LAS
              </a>
            </div>
          ))}
          </div>
          )}
        </section>

        {/* ---- Mesh Export card ---- */}
        <section
          className="p-5 flex flex-col gap-4"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <div>
            <h2
              className="text-base font-semibold"
              style={{ color: 'var(--text)', margin: 0 }}
            >
              Mesh Export
            </h2>
            <p
              className="text-sm mt-1"
              style={{ color: 'var(--text-muted)', margin: '4px 0 0' }}
            >
              Generate textured GLB/OBJ meshes from completed reconstructions.
            </p>
          </div>

          {reconstructionsLoading && (
            <p className="text-sm" style={{ color: 'var(--text-muted)', margin: 0 }}>
              Loading reconstructions…
            </p>
          )}

          {!reconstructionsLoading && (completedReconstructions ?? []).length === 0 && (
            <p className="text-sm" style={{ color: 'var(--text-muted)', margin: 0 }}>
              No completed reconstruction is ready for mesh export.
            </p>
          )}

          {(completedReconstructions ?? []).length > 0 && (
          <div style={{ borderTop: '1px solid var(--border)' }}>
          {(completedReconstructions ?? []).map((job) => (
            <MeshExportCard key={job.id} job={job} />
          ))}
          </div>
          )}
        </section>
      </div>
      </div>
    </div>
  )
}
