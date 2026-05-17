import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../../shared/api/client'
import { useMapStore } from '../../shared/stores/mapStore'
import type { Job } from '../../types/api'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

function useSessionJobs(sessionId: number | null) {
  return useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: () => get<Job[]>('/jobs/'),
    select: (jobs) => jobs.filter((j) => j.session_id === sessionId && j.status === 'complete'),
    enabled: sessionId !== null,
  })
}

function SplatCanvas({ reconstructionId }: { reconstructionId: number }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<unknown>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!containerRef.current) return

    let cancelled = false

    async function initViewer() {
      try {
        const { Viewer } = await import('@mkkellogg/gaussian-splats-3d')
        if (cancelled || !containerRef.current) return

        const viewer = new Viewer({
          cameraUp: [0, -1, 0],
          initialCameraPosition: [0, -1, -3],
          initialCameraLookAt: [0, 0, 0],
          rootElement: containerRef.current,
        })
        viewerRef.current = viewer

        const splatUrl = `${BASE_URL}/reconstruction/${reconstructionId}/splat?lod=preview`
        await viewer.addSplatScene(splatUrl, { streamView: true })
        if (!cancelled) {
          setLoading(false)
          viewer.start()
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load splat viewer')
          setLoading(false)
        }
      }
    }

    initViewer()

    return () => {
      cancelled = true
      if (viewerRef.current) {
        try {
          (viewerRef.current as { dispose?: () => void }).dispose?.()
        } catch {
          // ignore cleanup errors
        }
        viewerRef.current = null
      }
    }
  }, [reconstructionId])

  if (error) {
    return (
      <div
        style={{
          flex: 1, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 8,
        }}
      >
        <p style={{ color: 'var(--danger, #f85149)', fontSize: 13 }}>Viewer error: {error}</p>
        <a
          href={`${BASE_URL}/reconstruction/${reconstructionId}/splat?lod=full`}
          download={`splat_${reconstructionId}.ply`}
          style={{ color: '#58a6ff', fontSize: 13 }}
        >
          Download .ply instead
        </a>
      </div>
    )
  }

  return (
    <div style={{ position: 'relative', flex: 1 }}>
      {loading && (
        <div
          style={{
            position: 'absolute', inset: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'var(--bg)', zIndex: 10,
          }}
        >
          <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Loading splat…</p>
        </div>
      )}
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
    </div>
  )
}

export default function SplatViewerTab() {
  const { selectedSessionId } = useMapStore()
  const { data: completedJobs, isLoading } = useSessionJobs(selectedSessionId)
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)

  const jobs = completedJobs ?? []
  const activeId = selectedJobId ?? jobs[0]?.id ?? null

  if (selectedSessionId === null) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        Select a session first
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        Loading…
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        No completed reconstructions for this session. Start one in the Reconstruct tab.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
      {/* Sidebar */}
      <div
        style={{
          width: 200, padding: 16, borderRight: '1px solid var(--border)',
          background: 'var(--surface)', display: 'flex', flexDirection: 'column', gap: 8,
          overflowY: 'auto',
        }}
      >
        <p className="text-xs font-medium" style={{ color: 'var(--text-muted)', margin: '0 0 4px' }}>
          Reconstructions
        </p>
        {jobs.map((job) => (
          <button
            key={job.id}
            onClick={() => setSelectedJobId(job.id)}
            style={{
              background: activeId === job.id ? 'rgba(167,139,250,0.15)' : 'none',
              border: activeId === job.id ? '1px solid rgba(167,139,250,0.4)' : '1px solid transparent',
              borderRadius: 6, padding: '8px 10px', cursor: 'pointer',
              textAlign: 'left', fontFamily: 'inherit',
            }}
          >
            <p className="text-xs font-medium" style={{ color: 'var(--text)', margin: '0 0 2px' }}>
              #{job.id} — {job.preset}
            </p>
            <p className="text-xs" style={{ color: 'var(--text-muted)', margin: 0 }}>
              {job.frames_used} frames
            </p>
          </button>
        ))}
      </div>

      {/* Viewer */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#0a0a0a' }}>
        {activeId !== null ? (
          <SplatCanvas key={activeId} reconstructionId={activeId} />
        ) : (
          <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
            Select a reconstruction
          </div>
        )}
      </div>
    </div>
  )
}
