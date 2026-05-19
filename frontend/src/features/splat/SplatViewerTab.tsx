import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../../shared/api/client'
import { useMapStore } from '../../shared/stores/mapStore'
import type { Job, GeoTransform, Reconstruction, TrainingMetricPoint, CoverageGapCell } from '../../types/api'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const ACTIVE_STATUSES: string[] = ['pending', 'running_colmap', 'running_gsplat']

function useAllJobsForSession(sessionId: number | null) {
  return useQuery<Job[]>({
    queryKey: ['jobs', 'session', sessionId],
    queryFn: () => get<Job[]>('/jobs/'),
    select: (jobs) => jobs.filter((j) => j.session_id === sessionId),
    enabled: sessionId !== null,
    refetchInterval: (query) => {
      const jobs = query.state.data ?? []
      const hasRunning = jobs.some((j) => ACTIVE_STATUSES.includes(j.status))
      return hasRunning ? 2000 : 30_000
    },
  })
}

function useGeoTransform(reconstructionId: number | null) {
  return useQuery<GeoTransform>({
    queryKey: ['geo-transform', reconstructionId],
    queryFn: () => get<GeoTransform>(`/reconstruction/${reconstructionId!}/geo-transform`),
    enabled: reconstructionId !== null,
    staleTime: Infinity,
  })
}

function useReconstructionDetails(reconstructionId: number | null) {
  return useQuery<Reconstruction>({
    queryKey: ['reconstruction', 'details', reconstructionId],
    queryFn: () => get<Reconstruction>(`/reconstruction/${reconstructionId!}/status`),
    enabled: reconstructionId !== null,
    staleTime: Infinity,
  })
}

function useCoverageGaps(reconstructionId: number | null, isComplete: boolean) {
  return useQuery<CoverageGapCell[]>({
    queryKey: ['coverage-gaps', reconstructionId],
    queryFn: () => get<CoverageGapCell[]>(`/reconstruction/${reconstructionId!}/coverage-gaps`),
    enabled: reconstructionId !== null && isComplete,
    staleTime: Infinity,
    retry: false,
  })
}

const STATUS_STEP_LABEL: Record<string, string> = {
  pending: 'Queued…',
  running_colmap: 'COLMAP — feature extraction & matching',
  running_gsplat: 'Gaussian Splatting',
}

function RunningCard({ job }: { job: Job }) {
  const label = STATUS_STEP_LABEL[job.status] ?? job.step
  const barColor = job.status === 'pending' ? '#6b7280' : '#3b82f6'
  return (
    <div
      style={{
        padding: '10px 12px', borderRadius: 6,
        border: '1px solid #3b82f6',
        background: 'rgba(59,130,246,0.06)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 6 }}>
        <span style={{ color: 'var(--text)', fontWeight: 600 }}>
          #{job.id} · {job.preset}
        </span>
        <span style={{ color: '#60a5fa' }}>{job.progress_pct.toFixed(0)}%</span>
      </div>
      <div style={{ height: 4, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
        <div
          style={{
            height: '100%', background: barColor,
            width: `${job.progress_pct}%`, transition: 'width 0.6s ease',
          }}
        />
      </div>
      <div style={{ marginTop: 5, fontSize: 10, color: 'var(--text-muted)' }}>{label}</div>
    </div>
  )
}

function GeoTransformPanel({ reconstructionId }: { reconstructionId: number }) {
  const { data: geo } = useGeoTransform(reconstructionId)
  if (!geo) return null
  return (
    <div
      style={{
        marginTop: 8, padding: '6px 8px', borderRadius: 4,
        background: 'var(--bg)', fontSize: 10, color: 'var(--text-muted)',
        border: '1px solid var(--border)',
      }}
    >
      <div style={{ fontWeight: 600, color: 'var(--text)', marginBottom: 3, fontSize: 10 }}>
        Geo-Transform
      </div>
      <div>UTM {geo.utm_zone}</div>
      <div>Scale {geo.scale.toExponential(3)}</div>
      <div>
        Origin {geo.utm_origin[0].toFixed(0)}E {geo.utm_origin[1].toFixed(0)}N
      </div>
    </div>
  )
}

function TrainingMetricsPanel({ metrics }: { metrics: TrainingMetricPoint[] }) {
  const iters = metrics.map((m) => m.iter)
  const psnrVals = metrics.map((m) => m.psnr)
  const ssimVals = metrics.map((m) => m.ssim)

  function toPolyline(values: number[], color: string) {
    const minV = Math.min(...values)
    const maxV = Math.max(...values)
    const range = maxV - minV || 1
    const w = 72
    const h = 28
    const points = values.map((v, i) => {
      const x = iters.length === 1 ? w / 2 : (i / (iters.length - 1)) * w
      const y = h - ((v - minV) / range) * (h - 4) - 2
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    return (
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    )
  }

  const finalPsnr = psnrVals[psnrVals.length - 1]
  const finalSsim = ssimVals[ssimVals.length - 1]

  return (
    <div
      style={{
        marginTop: 8, padding: '6px 8px', borderRadius: 4,
        background: 'var(--bg)', border: '1px solid var(--border)',
      }}
    >
      <div style={{ fontWeight: 600, color: 'var(--text)', marginBottom: 6, fontSize: 10 }}>
        Training Quality
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 2 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 8 }}>PSNR</span>
            <span style={{ color: '#86efac', fontSize: 9, fontWeight: 700 }}>
              {finalPsnr.toFixed(1)} dB
            </span>
          </div>
          <svg viewBox="0 0 72 28" style={{ width: '100%', height: 28, display: 'block' }}>
            {toPolyline(psnrVals, '#86efac')}
          </svg>
          <div style={{ color: 'var(--text-muted)', fontSize: 7, textAlign: 'center' }}>pixel accuracy</div>
        </div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 2 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 8 }}>SSIM</span>
            <span style={{ color: '#60a5fa', fontSize: 9, fontWeight: 700 }}>
              {finalSsim.toFixed(2)}
            </span>
          </div>
          <svg viewBox="0 0 72 28" style={{ width: '100%', height: 28, display: 'block' }}>
            {toPolyline(ssimVals, '#60a5fa')}
          </svg>
          <div style={{ color: 'var(--text-muted)', fontSize: 7, textAlign: 'center' }}>looks-like score</div>
        </div>
      </div>
    </div>
  )
}

const GAP_COLORS: Record<string, number> = {
  sparse: 0xeab308,
  thin: 0xf97316,
  very_sparse: 0xef4444,
}

const GAP_OPACITY: Record<string, number> = {
  sparse: 0.35,
  thin: 0.35,
  very_sparse: 0.40,
}

interface SplatCanvasProps {
  reconstructionId: number
  coverageGaps: CoverageGapCell[] | null
  showCoverageGaps: boolean
}

function SplatCanvas({ reconstructionId, coverageGaps, showCoverageGaps }: SplatCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<unknown>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const gapGroupRef = useRef<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [viewerReady, setViewerReady] = useState(false)

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
          setViewerReady(true)
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
      setViewerReady(false)
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

  // Build/rebuild coverage gap meshes when data or visibility changes
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const viewer = viewerRef.current as any
    if (!viewer?.scene) return

    const scene = viewer.scene

    // Remove old group
    if (gapGroupRef.current) {
      scene.remove(gapGroupRef.current)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      gapGroupRef.current.traverse((obj: any) => {
        if (obj.isMesh) {
          obj.geometry.dispose()
          obj.material.dispose()
        }
      })
      gapGroupRef.current = null
    }

    if (!coverageGaps || !showCoverageGaps || coverageGaps.length === 0) return

    let cancelled = false
    import('three').then((THREE) => {
      if (cancelled) return
      const group = new THREE.Group()
      for (const cell of coverageGaps) {
        const geo = new THREE.BoxGeometry(cell.size, cell.size, cell.size)
        const mat = new THREE.MeshBasicMaterial({
          color: GAP_COLORS[cell.level] ?? 0xffffff,
          transparent: true,
          opacity: GAP_OPACITY[cell.level] ?? 0.35,
          depthWrite: false,
        })
        const mesh = new THREE.Mesh(geo, mat)
        mesh.position.set(cell.x, cell.y, cell.z)
        group.add(mesh)
      }
      scene.add(group)
      gapGroupRef.current = group
    })

    return () => {
      cancelled = true
      if (gapGroupRef.current) {
        scene.remove(gapGroupRef.current)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        gapGroupRef.current.traverse((obj: any) => {
          if (obj.isMesh) {
            obj.geometry.dispose()
            obj.material.dispose()
          }
        })
        gapGroupRef.current = null
      }
    }
  }, [coverageGaps, showCoverageGaps, viewerReady])

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
  const { selectedSessionId, targetSessionId, setTargetSessionId } = useMapStore()
  const { data: allJobs, isLoading } = useAllJobsForSession(selectedSessionId)
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [showCoverageGaps, setShowCoverageGaps] = useState(false)

  const jobs = allJobs ?? []
  const running = jobs.filter((j) => ACTIVE_STATUSES.includes(j.status))
  const completed = jobs.filter((j) => j.status === 'complete')
  const activeId = selectedJobId ?? completed[0]?.id ?? null
  const { data: reconstructionDetails } = useReconstructionDetails(activeId)
  const selectedJobComplete = completed.some((j) => j.id === activeId)
  const { data: coverageGaps, isFetching: gapsFetching } = useCoverageGaps(
    activeId,
    selectedJobComplete ?? false,
  )

  useEffect(() => {
    if (targetSessionId == null) return
    const completedJobs = (allJobs ?? []).filter((j) => j.status === 'complete')
    const match = [...completedJobs]
      .sort((a, b) => b.id - a.id)
      .find((j) => j.session_id === targetSessionId)
    if (match) {
      setSelectedJobId(match.id)
      setTargetSessionId(null)
    }
  }, [targetSessionId, allJobs, setTargetSessionId])

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

  if (running.length === 0 && completed.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        No reconstructions for this session. Start one in the Reconstruct tab.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
      {/* Sidebar */}
      <div
        style={{
          width: 200, padding: 12, borderRight: '1px solid var(--border)',
          background: 'var(--surface)', display: 'flex', flexDirection: 'column', gap: 8,
          overflowY: 'auto',
        }}
      >
        {running.length > 0 && (
          <>
            <p className="text-xs font-medium" style={{ color: 'var(--text-muted)', margin: '4px 0 2px' }}>
              In Progress
            </p>
            {running.map((job) => <RunningCard key={job.id} job={job} />)}
          </>
        )}
        {completed.length > 0 && (
          <>
            <p
              className="text-xs font-medium"
              style={{ color: 'var(--text-muted)', margin: running.length > 0 ? '8px 0 2px' : '4px 0 2px' }}
            >
              Completed
            </p>
            {completed.map((job) => (
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
          </>
        )}
        {activeId !== null && <GeoTransformPanel reconstructionId={activeId} />}
        {reconstructionDetails?.training_metrics && (
          <TrainingMetricsPanel metrics={reconstructionDetails.training_metrics} />
        )}
        {activeId !== null && selectedJobComplete && (
          <div style={{ marginTop: 8 }}>
            <button
              onClick={() => setShowCoverageGaps((v) => !v)}
              disabled={gapsFetching}
              style={{
                width: '100%',
                padding: '4px 8px',
                borderRadius: 4,
                border: '1px solid var(--border)',
                background: showCoverageGaps ? 'rgba(239,68,68,0.15)' : 'var(--bg)',
                color: showCoverageGaps ? '#f87171' : 'var(--text-muted)',
                cursor: gapsFetching ? 'default' : 'pointer',
                fontFamily: 'inherit',
                fontSize: 11,
                textAlign: 'left',
              }}
            >
              {gapsFetching ? '⟳ Computing…' : showCoverageGaps ? '◉ Coverage Gaps' : '○ Coverage Gaps'}
            </button>
            {showCoverageGaps && !gapsFetching && coverageGaps && coverageGaps.length > 0 && (
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 4, flexWrap: 'wrap' }}>
                {[
                  { color: '#eab308', label: 'sparse' },
                  { color: '#f97316', label: 'thin' },
                  { color: '#ef4444', label: 'very sparse' },
                ].map(({ color, label }) => (
                  <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 9, color: 'var(--text-muted)' }}>
                    <span style={{ width: 8, height: 8, background: color, borderRadius: 1, display: 'inline-block', opacity: 0.7 }} />
                    {label}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Viewer */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#0a0a0a' }}>
        {activeId !== null ? (
          <SplatCanvas
            key={activeId}
            reconstructionId={activeId}
            coverageGaps={coverageGaps ?? null}
            showCoverageGaps={showCoverageGaps}
          />
        ) : (
          <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
            {running.length > 0 ? 'Reconstruction in progress…' : 'Select a reconstruction'}
          </div>
        )}
      </div>
    </div>
  )
}
