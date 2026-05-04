import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { get, post } from '../../shared/api/client'
import { useMapStore } from '../../shared/stores/mapStore'
import { useToast } from '../../shared/hooks/useToast'
import { Button } from '../../shared/components/Button'
import type { Session, Image } from '../../types/api'

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

// ---- main component ----

export default function ExportTab() {
  const { selectedSessionId } = useMapStore()
  const { addToast } = useToast()

  const { data: session, isLoading: sessionLoading } = useSession(selectedSessionId)

  // WebODM export state
  const [webodmResult, setWebodmResult] = useState<{ zip_path: string; image_count: number } | null>(null)

  const webodmMutation = useMutation({
    mutationFn: () =>
      post<{ zip_path: string; image_count: number }>(
        `/export/webodm?session_id=${selectedSessionId}`
      ),
    onSuccess: (data) => {
      setWebodmResult(data)
    },
    onError: (err: Error) => {
      addToast(`WebODM export failed: ${err.message}`, 'error')
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

    addToast(`GeoJSON downloaded — ${gpsImages.length} features`, 'success')
  }

  // ---- guard: no session selected ----
  if (selectedSessionId === null) {
    return (
      <div
        className="flex-1 flex items-center justify-center"
        style={{ color: 'var(--text-muted)' }}
      >
        Select a session first
      </div>
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
  const zipFilename = webodmResult
    ? webodmResult.zip_path.split(/[/\\]/).at(-1) ?? webodmResult.zip_path
    : null

  return (
    <div
      className="flex-1 overflow-y-auto p-6"
      style={{ color: 'var(--text)' }}
    >
      <div
        className="mx-auto flex flex-col gap-6"
        style={{ maxWidth: 640 }}
      >
        {/* ---- Session summary card ---- */}
        <section
          className="rounded-lg p-5 flex flex-col gap-3"
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

        {/* ---- WebODM Export card ---- */}
        <section
          className="rounded-lg p-5 flex flex-col gap-4"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <div>
            <h2
              className="text-base font-semibold"
              style={{ color: 'var(--text)', margin: 0 }}
            >
              WebODM Package
            </h2>
            <p
              className="text-sm mt-1"
              style={{ color: 'var(--text-muted)', margin: '4px 0 0' }}
            >
              Bundle usable frames into a zip for WebODM processing.
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
              {webodmMutation.isPending ? 'Building…' : 'Download WebODM Package'}
            </Button>

            {webodmResult && (
              <div
                className="rounded px-3 py-2 text-sm flex flex-col gap-0.5"
                style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}
              >
                <span style={{ color: '#4ade80', fontWeight: 600 }}>
                  Ready — {webodmResult.image_count} images
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
          className="rounded-lg p-5 flex flex-col gap-4"
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
      </div>
    </div>
  )
}
