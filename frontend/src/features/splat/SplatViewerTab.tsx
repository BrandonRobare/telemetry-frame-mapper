import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, del } from '../../shared/api/client'
import { useMapStore } from '../../shared/stores/mapStore'
import type {
  Job,
  GeoTransform,
  Reconstruction,
  TrainingMetricPoint,
  CoverageGapCell,
  Annotation,
  FlythroughStatus,
} from '../../types/api'
import { worldToGps, useRayCast } from './useViewerCoords'
import MiniLeafletPane from './MiniLeafletPane'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const ACTIVE_STATUSES: string[] = ['pending', 'running_colmap', 'running_gsplat']

type ActiveTool = 'none' | 'annotate' | 'measure-dist' | 'measure-area'

interface MeasurePoint {
  worldPos: { x: number; y: number; z: number }
  gps: { lat: number; lon: number; alt: number }
}

interface FlythroughKeyframe {
  position: [number, number, number]
  target: [number, number, number]
  duration_s: number
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

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

function useAnnotations(reconstructionId: number | null) {
  return useQuery<Annotation[]>({
    queryKey: ['annotations', reconstructionId],
    queryFn: () => get<Annotation[]>(`/reconstruction/${reconstructionId!}/annotations`),
    enabled: reconstructionId !== null,
    staleTime: 30_000,
  })
}

function useFlythroughStatus(reconstructionId: number | null) {
  return useQuery<FlythroughStatus>({
    queryKey: ['flythrough-status', reconstructionId],
    queryFn: () => get<FlythroughStatus>(`/reconstruction/${reconstructionId!}/flythrough/status`),
    enabled: reconstructionId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.flythrough_status
      return status === 'pending' || status === 'running' ? 2000 : false
    },
  })
}

// ---------------------------------------------------------------------------
// Small UI components
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Label popover — shown after a canvas click in annotate mode
// ---------------------------------------------------------------------------

interface LabelPopoverProps {
  screenX: number
  screenY: number
  onSave: (label: string, color: string) => void
  onCancel: () => void
}

function LabelPopover({ screenX, screenY, onSave, onCancel }: LabelPopoverProps) {
  const [label, setLabel] = useState('')
  const [color, setColor] = useState('#ff6b35')

  return (
    <div
      style={{
        position: 'absolute',
        left: Math.min(screenX + 8, window.innerWidth - 200),
        top: Math.min(screenY + 8, window.innerHeight - 120),
        zIndex: 100,
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '10px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        width: 180,
        boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
      }}
    >
      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)' }}>New annotation</div>
      <input
        autoFocus
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && label.trim()) onSave(label.trim(), color)
          if (e.key === 'Escape') onCancel()
        }}
        placeholder="Label…"
        style={{
          background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 4,
          color: 'var(--text)', fontSize: 12, padding: '4px 6px', fontFamily: 'inherit',
          outline: 'none',
        }}
      />
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <label style={{ fontSize: 10, color: 'var(--text-muted)', flex: 1 }}>Color</label>
        <input
          type="color"
          value={color}
          onChange={(e) => setColor(e.target.value)}
          style={{ width: 28, height: 22, border: 'none', background: 'none', cursor: 'pointer', padding: 0 }}
        />
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <button
          onClick={() => label.trim() && onSave(label.trim(), color)}
          disabled={!label.trim()}
          style={{
            flex: 1, padding: '4px 0', borderRadius: 4, border: 'none',
            background: label.trim() ? '#7c3aed' : 'var(--border)',
            color: label.trim() ? '#fff' : 'var(--text-muted)',
            cursor: label.trim() ? 'pointer' : 'default',
            fontSize: 11, fontFamily: 'inherit',
          }}
        >
          Save
        </button>
        <button
          onClick={onCancel}
          style={{
            flex: 1, padding: '4px 0', borderRadius: 4,
            border: '1px solid var(--border)', background: 'none',
            color: 'var(--text-muted)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit',
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Measurement layer — renders Three.js lines + labels (ephemeral, no backend)
// ---------------------------------------------------------------------------

function makeLabelTexture(text: string): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 48
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = 'rgba(0,0,0,0.7)'
  ctx.roundRect(2, 2, canvas.width - 4, canvas.height - 4, 6)
  ctx.fill()
  ctx.fillStyle = '#ffffff'
  ctx.font = 'bold 22px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, canvas.width / 2, canvas.height / 2)
  return canvas
}

interface MeasurementLayerProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  viewerRef: React.RefObject<any>
  viewerReady: boolean
  points: MeasurePoint[]
  mode: 'measure-dist' | 'measure-area' | null
}

function useMeasurementLayer({ viewerRef, viewerReady, points, mode }: MeasurementLayerProps) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const groupRef = useRef<any>(null)

  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer?.scene) return
    const scene = viewer.scene

    if (groupRef.current) {
      scene.remove(groupRef.current)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      groupRef.current.traverse((obj: any) => {
        obj.geometry?.dispose()
        if (obj.material?.map) obj.material.map.dispose()
        obj.material?.dispose()
      })
      groupRef.current = null
    }

    if (points.length < 2) return

    let cancelled = false
    import('three').then(async (THREE) => {
      if (cancelled) return

      const group = new THREE.Group()

      // Line through all points
      const positions = points.map((p) => new THREE.Vector3(p.worldPos.x, p.worldPos.y, p.worldPos.z))
      if (mode === 'measure-area' && positions.length >= 3) {
        positions.push(positions[0]) // close the polygon
      }
      const geom = new THREE.BufferGeometry().setFromPoints(positions)
      const mat = new THREE.LineDashedMaterial({ color: 0xfacc15, dashSize: 0.1, gapSize: 0.05, linewidth: 1 })
      const line = new THREE.Line(geom, mat)
      line.computeLineDistances()
      group.add(line)

      // Polygon fill for area mode
      if (mode === 'measure-area' && points.length >= 3) {
        const shape = new THREE.Shape(points.map((p) => new THREE.Vector2(p.worldPos.x, p.worldPos.z)))
        const fillGeo = new THREE.ShapeGeometry(shape)
        // Rotate to lie in the XZ plane (Y up)
        const pos = fillGeo.attributes.position
        for (let i = 0; i < pos.count; i++) {
          const x = pos.getX(i)
          const z = pos.getY(i)
          pos.setXYZ(i, x, points[0].worldPos.y, z)
        }
        pos.needsUpdate = true
        const fillMat = new THREE.MeshBasicMaterial({
          color: 0xfacc15, transparent: true, opacity: 0.18, side: THREE.DoubleSide, depthWrite: false,
        })
        group.add(new THREE.Mesh(fillGeo, fillMat))
      }

      // Label sprite
      let labelText = ''
      if (mode === 'measure-dist' && points.length >= 2) {
        const distance = await import('@turf/distance').then(({ default: turfDist }) =>
          turfDist(
            [points[0].gps.lon, points[0].gps.lat],
            [points[points.length - 1].gps.lon, points[points.length - 1].gps.lat],
            { units: 'meters' },
          )
        )
        labelText = distance >= 1000 ? `${(distance / 1000).toFixed(2)} km` : `${distance.toFixed(1)} m`
      } else if (mode === 'measure-area' && points.length >= 3) {
        const area = await import('@turf/area').then(({ default: turfArea }) => {
          const coords = [...points.map((p): [number, number] => [p.gps.lon, p.gps.lat])]
          coords.push(coords[0])
          return turfArea({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] }, properties: {} })
        })
        labelText = area >= 10000 ? `${(area / 10000).toFixed(2)} ha` : `${area.toFixed(0)} m²`
      }

      if (labelText) {
        const mid = positions[Math.floor((positions.length - 1) / 2)]
        const tex = new THREE.CanvasTexture(makeLabelTexture(labelText))
        const spriteMat = new THREE.SpriteMaterial({ map: tex, depthTest: false })
        const sprite = new THREE.Sprite(spriteMat)
        sprite.position.copy(mid)
        sprite.scale.set(0.6, 0.12, 1)
        group.add(sprite)
      }

      if (!cancelled) {
        scene.add(group)
        groupRef.current = group
      }
    })

    return () => {
      cancelled = true
      if (groupRef.current) {
        scene.remove(groupRef.current)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        groupRef.current.traverse((obj: any) => {
          obj.geometry?.dispose()
          if (obj.material?.map) obj.material.map.dispose()
          obj.material?.dispose()
        })
        groupRef.current = null
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, mode, viewerReady])
}

// ---------------------------------------------------------------------------
// Coverage gap constants
// ---------------------------------------------------------------------------

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

interface FlythroughControlsProps {
  reconstructionId: number
  keyframeCount: number
  recording: boolean
  message: string | null
  status: FlythroughStatus | undefined
  onAddKeyframe: () => void
  onPreview: () => void
  onRecord: () => void
  onServerRender: () => void
}

function FlythroughControls({
  reconstructionId,
  keyframeCount,
  recording,
  message,
  status,
  onAddKeyframe,
  onPreview,
  onRecord,
  onServerRender,
}: FlythroughControlsProps) {
  const canRun = keyframeCount >= 2 && !recording
  const serverRunning = status?.flythrough_status === 'pending' || status?.flythrough_status === 'running'
  const btnStyle = {
    padding: '4px 8px',
    borderRadius: 4,
    border: '1px solid var(--border)',
    background: 'var(--bg)',
    color: 'var(--text-muted)',
    cursor: 'pointer',
    fontSize: 11,
    fontFamily: 'inherit',
  }

  return (
    <div
      style={{
        position: 'absolute',
        right: 12,
        top: 12,
        zIndex: 20,
        width: 220,
        padding: 10,
        borderRadius: 6,
        background: 'rgba(13,17,23,0.88)',
        border: '1px solid rgba(139,148,158,0.35)',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ color: 'var(--text)', fontSize: 11, fontWeight: 700 }}>Flythrough</span>
        <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>{keyframeCount} keyframes</span>
      </div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        <button type="button" onClick={onAddKeyframe} style={btnStyle}>Add Keyframe</button>
        <button type="button" onClick={onPreview} disabled={!canRun} style={{ ...btnStyle, opacity: canRun ? 1 : 0.5 }}>
          Preview
        </button>
        <button type="button" onClick={onRecord} disabled={!canRun} style={{ ...btnStyle, opacity: canRun ? 1 : 0.5 }}>
          {recording ? 'Recording…' : 'Record'}
        </button>
        <button
          type="button"
          onClick={onServerRender}
          disabled={!canRun || serverRunning}
          style={{ ...btnStyle, opacity: canRun && !serverRunning ? 1 : 0.5 }}
        >
          {serverRunning ? 'Rendering…' : 'Server MP4'}
        </button>
      </div>
      {message && (
        <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 10 }}>{message}</p>
      )}
      {status?.flythrough_status === 'failed' && status.flythrough_error && (
        <p style={{ margin: 0, color: 'var(--danger, #f85149)', fontSize: 10 }}>
          {status.flythrough_error}
        </p>
      )}
      {status?.flythrough_status === 'complete' && status.flythrough_path && (
        <a
          href={`${BASE_URL}/reconstruction/${reconstructionId}/flythrough`}
          download={`flythrough_${reconstructionId}.mp4`}
          style={{ color: '#58a6ff', fontSize: 11, textDecoration: 'none' }}
        >
          Download server MP4
        </a>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SplatCanvas
// ---------------------------------------------------------------------------

interface PendingAnnotation {
  worldPos: { x: number; y: number; z: number }
  screenPos: { x: number; y: number }
}

interface SplatCanvasProps {
  reconstructionId: number
  coverageGaps: CoverageGapCell[] | null
  showCoverageGaps: boolean
  activeTool: ActiveTool
  geoTransform: GeoTransform | undefined
  annotations: Annotation[]
  onAnnotationCreated: () => void
  measurePoints: MeasurePoint[]
  measureMode: 'measure-dist' | 'measure-area' | null
  onMeasurePoint: (pt: MeasurePoint) => void
  onMeasureClose: () => void
}

function SplatCanvas({
  reconstructionId,
  coverageGaps,
  showCoverageGaps,
  activeTool,
  geoTransform,
  annotations,
  onAnnotationCreated,
  measurePoints,
  measureMode,
  onMeasurePoint,
  onMeasureClose,
}: SplatCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<unknown>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const gapGroupRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const annotationGroupRef = useRef<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [viewerReady, setViewerReady] = useState(false)
  const [pendingAnnotation, setPendingAnnotation] = useState<PendingAnnotation | null>(null)
  const [flythroughKeyframes, setFlythroughKeyframes] = useState<FlythroughKeyframe[]>([])
  const [recording, setRecording] = useState(false)
  const [flythroughMessage, setFlythroughMessage] = useState<string | null>(null)

  const queryClient = useQueryClient()
  const { data: flythroughStatus } = useFlythroughStatus(reconstructionId)
  const { castRay } = useRayCast(
    viewerRef as React.RefObject<unknown>,
    containerRef,
  )

  useMeasurementLayer({ viewerRef: viewerRef as React.RefObject<unknown>, viewerReady, points: measurePoints, mode: measureMode })

  const createAnnotation = useMutation({
    mutationFn: (body: { label: string; lat: number; lon: number; alt_m: number; color: string }) =>
      post<Annotation>(`/reconstruction/${reconstructionId}/annotations`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['annotations', reconstructionId] })
      onAnnotationCreated()
    },
  })

  const renderVideo = useMutation({
    mutationFn: (keyframes: FlythroughKeyframe[]) =>
      post<FlythroughStatus>(`/reconstruction/${reconstructionId}/render-video`, { keyframes }),
    onSuccess: () => {
      setFlythroughMessage('Server render queued.')
      queryClient.invalidateQueries({ queryKey: ['flythrough-status', reconstructionId] })
    },
    onError: (err: Error) => setFlythroughMessage(err.message),
  })

  function captureCurrentKeyframe() {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const viewer = viewerRef.current as any
    const camera = viewer?.camera
    if (!camera) {
      setFlythroughMessage('Camera is not ready.')
      return
    }
    const controls = viewer.orbitControls ?? viewer.controls ?? null
    const target = controls?.target ?? { x: 0, y: 0, z: 0 }
    setFlythroughKeyframes((prev) => [
      ...prev,
      {
        position: [camera.position.x, camera.position.y, camera.position.z],
        target: [target.x, target.y, target.z],
        duration_s: 3,
      },
    ])
    setFlythroughMessage('Keyframe saved.')
  }

  function previewFlythrough(): Promise<void> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const viewer = viewerRef.current as any
    const camera = viewer?.camera
    const controls = viewer?.orbitControls ?? viewer?.controls ?? null
    if (!camera || flythroughKeyframes.length < 2) {
      setFlythroughMessage('Add at least two keyframes.')
      return Promise.resolve()
    }

    return new Promise((resolve) => {
      let segment = 0
      let startTime: number | null = null

      function step(now: number) {
        const current = flythroughKeyframes[segment]
        const next = flythroughKeyframes[segment + 1]
        if (!current || !next) {
          resolve()
          return
        }
        if (startTime === null) startTime = now
        const durationMs = Math.max(250, next.duration_s * 1000)
        const t = Math.min(1, (now - startTime) / durationMs)
        const ease = t * t * (3 - 2 * t)
        const pos = current.position.map((value, i) =>
          value + (next.position[i] - value) * ease
        )
        const target = current.target.map((value, i) =>
          value + (next.target[i] - value) * ease
        )
        camera.position.set(pos[0], pos[1], pos[2])
        if (controls?.target?.set) controls.target.set(target[0], target[1], target[2])
        controls?.update?.()
        if (t < 1) {
          window.requestAnimationFrame(step)
          return
        }
        segment += 1
        startTime = now
        if (segment >= flythroughKeyframes.length - 1) {
          resolve()
        } else {
          window.requestAnimationFrame(step)
        }
      }

      window.requestAnimationFrame(step)
    })
  }

  function downloadBlob(blob: Blob, extension: 'mp4' | 'webm') {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `flythrough_${reconstructionId}.${extension}`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function recordFlythrough() {
    const canvas = containerRef.current?.querySelector('canvas') as HTMLCanvasElement | null
    if (!canvas?.captureStream || typeof MediaRecorder === 'undefined') {
      setFlythroughMessage('Browser recording is not available here; use Server MP4.')
      return
    }
    const mimeCandidates = [
      'video/mp4;codecs=h264',
      'video/mp4',
      'video/webm;codecs=vp9',
      'video/webm',
    ]
    const mimeType = mimeCandidates.find((mime) => MediaRecorder.isTypeSupported(mime)) ?? ''
    const extension = mimeType.includes('mp4') ? 'mp4' : 'webm'
    const stream = canvas.captureStream(30)
    const chunks: BlobPart[] = []
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data)
    }
    recorder.onstop = () => {
      downloadBlob(new Blob(chunks, { type: mimeType || 'video/webm' }), extension)
      stream.getTracks().forEach((track) => track.stop())
      setRecording(false)
      setFlythroughMessage(`Downloaded ${extension.toUpperCase()} flythrough.`)
    }
    setRecording(true)
    setFlythroughMessage('Recording browser flythrough…')
    recorder.start()
    await previewFlythrough()
    recorder.stop()
  }

  // Viewer init
  useEffect(() => {
    if (!containerRef.current) return
    let cancelled = false

    async function initViewer() {
      try {
        const { Viewer, SceneFormat } = await import('@mkkellogg/gaussian-splats-3d')
        if (cancelled || !containerRef.current) return

        const viewer = new Viewer({
          cameraUp: [0, -1, 0],
          initialCameraPosition: [0, -1, -3],
          initialCameraLookAt: [0, 0, 0],
          rootElement: containerRef.current,
        })
        viewerRef.current = viewer

        const splatUrl = `${BASE_URL}/reconstruction/${reconstructionId}/splat?lod=preview`
        await viewer.addSplatScene(splatUrl, { streamView: true, format: SceneFormat.Ply })
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

  // Sync 3D camera → Leaflet via syncedViewport
  useEffect(() => {
    if (!viewerReady || !geoTransform) return
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const viewer = viewerRef.current as any
    if (!viewer) return

    const controls = viewer.orbitControls ?? viewer.controls ?? null
    if (!controls) return

    function onCameraChange() {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const v = viewerRef.current as any
      if (!v?.camera || !geoTransform) return
      const cam = v.camera
      const gps = worldToGps({ x: cam.position.x, y: cam.position.y, z: cam.position.z }, geoTransform)
      if (!gps) return
      const dist = cam.position.distanceTo(controls.target)
      const zoom = Math.max(1, Math.min(20, Math.round(20 - Math.log2(Math.max(dist, 0.001)))))
      useMapStore.getState().setSyncedViewport({ lat: gps.lat, lon: gps.lon, zoom, source: '3d' })
    }

    controls.addEventListener('change', onCameraChange)
    return () => controls.removeEventListener('change', onCameraChange)
  }, [viewerReady, geoTransform])

  // Canvas click handler for annotate mode
  useEffect(() => {
    const container = containerRef.current
    if (!container || !viewerReady) return
    if (activeTool !== 'annotate') {
      container.style.cursor = ''
      return
    }

    container.style.cursor = 'crosshair'

    function handleClick(e: MouseEvent) {
      if (activeTool === 'annotate') {
        castRay(e).then((result) => {
          if (result) setPendingAnnotation(result)
        })
      } else if (activeTool === 'measure-dist' || activeTool === 'measure-area') {
        castRay(e).then((result) => {
          if (!result || !geoTransform) return
          const gps = worldToGps(result.worldPos, geoTransform)
          if (!gps) return
          onMeasurePoint({ worldPos: result.worldPos, gps })
        })
      }
    }

    function handleDblClick(e: MouseEvent) {
      if (activeTool === 'measure-area') {
        e.preventDefault()
        onMeasureClose()
      }
    }

    container.addEventListener('click', handleClick)
    container.addEventListener('dblclick', handleDblClick)
    return () => {
      container.removeEventListener('click', handleClick)
      container.removeEventListener('dblclick', handleDblClick)
      container.style.cursor = ''
    }
  }, [activeTool, viewerReady, castRay, geoTransform, onMeasurePoint, onMeasureClose])

  // Coverage gap meshes
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const viewer = viewerRef.current as any
    if (!viewer?.scene) return

    const scene = viewer.scene
    if (gapGroupRef.current) {
      scene.remove(gapGroupRef.current)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      gapGroupRef.current.traverse((obj: any) => {
        if (obj.isMesh) { obj.geometry.dispose(); obj.material.dispose() }
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
          if (obj.isMesh) { obj.geometry.dispose(); obj.material.dispose() }
        })
        gapGroupRef.current = null
      }
    }
  }, [coverageGaps, showCoverageGaps, viewerReady])

  // Annotation sprites
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const viewer = viewerRef.current as any
    if (!viewer?.scene) return

    const scene = viewer.scene
    if (annotationGroupRef.current) {
      scene.remove(annotationGroupRef.current)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      annotationGroupRef.current.traverse((obj: any) => {
        if (obj.isSprite) { obj.material.map?.dispose(); obj.material.dispose() }
      })
      annotationGroupRef.current = null
    }

    if (!annotations.length || !geoTransform) return

    let cancelled = false
    import('three').then(async (THREE) => {
      if (cancelled) return
      const group = new THREE.Group()
      const { gpsToWorld } = await import('./useViewerCoords')

      for (const ann of annotations) {
        const wp = gpsToWorld({ lat: ann.lat, lon: ann.lon, alt: ann.alt_m }, geoTransform)
        if (!wp) continue

        // Draw label on a canvas texture
        const canvas = document.createElement('canvas')
        canvas.width = 256
        canvas.height = 64
        const ctx = canvas.getContext('2d')!
        ctx.fillStyle = ann.color
        ctx.roundRect(4, 4, canvas.width - 8, canvas.height - 8, 8)
        ctx.fill()
        ctx.fillStyle = '#ffffff'
        ctx.font = 'bold 24px sans-serif'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(ann.label, canvas.width / 2, canvas.height / 2)

        const texture = new THREE.CanvasTexture(canvas)
        const mat = new THREE.SpriteMaterial({ map: texture, depthTest: false })
        const sprite = new THREE.Sprite(mat)
        sprite.position.set(wp.x, wp.y, wp.z)
        sprite.scale.set(0.5, 0.125, 1)
        group.add(sprite)
      }

      scene.add(group)
      annotationGroupRef.current = group
    })

    return () => {
      cancelled = true
      if (annotationGroupRef.current) {
        scene.remove(annotationGroupRef.current)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        annotationGroupRef.current.traverse((obj: any) => {
          if (obj.isSprite) { obj.material.map?.dispose(); obj.material.dispose() }
        })
        annotationGroupRef.current = null
      }
    }
  }, [annotations, geoTransform, viewerReady])

  if (error) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
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
      {viewerReady && (
        <FlythroughControls
          reconstructionId={reconstructionId}
          keyframeCount={flythroughKeyframes.length}
          recording={recording}
          message={flythroughMessage}
          status={flythroughStatus}
          onAddKeyframe={captureCurrentKeyframe}
          onPreview={() => {
            previewFlythrough().then(() => setFlythroughMessage('Preview complete.'))
          }}
          onRecord={() => { void recordFlythrough() }}
          onServerRender={() => renderVideo.mutate(flythroughKeyframes)}
        />
      )}
      {pendingAnnotation && geoTransform && (
        <LabelPopover
          screenX={pendingAnnotation.screenPos.x}
          screenY={pendingAnnotation.screenPos.y}
          onSave={(label, color) => {
            const gps = worldToGps(pendingAnnotation.worldPos, geoTransform)
            if (gps) {
              createAnnotation.mutate({ label, lat: gps.lat, lon: gps.lon, alt_m: gps.alt, color })
            }
            setPendingAnnotation(null)
          }}
          onCancel={() => setPendingAnnotation(null)}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Viewer toolbar
// ---------------------------------------------------------------------------

interface ViewerToolbarProps {
  activeTool: ActiveTool
  onToolChange: (tool: ActiveTool) => void
  geoTransformAvailable: boolean
  hasMeasurePoints: boolean
  onClearMeasure: () => void
}

function ViewerToolbar({
  activeTool,
  onToolChange,
  geoTransformAvailable,
  hasMeasurePoints,
  onClearMeasure,
}: ViewerToolbarProps) {
  function toolBtn(tool: ActiveTool, label: string, title: string) {
    const active = activeTool === tool
    return (
      <button
        key={tool}
        title={title}
        onClick={() => onToolChange(active ? 'none' : tool)}
        style={{
          padding: '4px 8px', borderRadius: 4, fontSize: 11,
          border: active ? '1px solid #7c3aed' : '1px solid var(--border)',
          background: active ? 'rgba(124,58,237,0.15)' : 'var(--bg)',
          color: active ? '#a78bfa' : 'var(--text-muted)',
          cursor: geoTransformAvailable ? 'pointer' : 'not-allowed',
          fontFamily: 'inherit',
          opacity: geoTransformAvailable ? 1 : 0.5,
        }}
        disabled={!geoTransformAvailable}
      >
        {label}
      </button>
    )
  }

  const noGeo = 'Geo-transform unavailable'
  return (
    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 8 }}>
      {toolBtn('annotate', '⊕ Annotate', geoTransformAvailable ? 'Place GPS annotation' : noGeo)}
      {toolBtn('measure-dist', '↔ Distance', geoTransformAvailable ? 'Measure distance between two points' : noGeo)}
      {toolBtn('measure-area', '⬡ Area', geoTransformAvailable ? 'Measure polygon area (double-click to close)' : noGeo)}
      {hasMeasurePoints && (
        <button
          onClick={onClearMeasure}
          style={{
            padding: '4px 8px', borderRadius: 4, fontSize: 11,
            border: '1px solid var(--border)', background: 'var(--bg)',
            color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'inherit',
          }}
          title="Clear measurements"
        >
          ✕ Clear
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Annotations list in sidebar
// ---------------------------------------------------------------------------

interface AnnotationsListProps {
  reconstructionId: number
  annotations: Annotation[]
}

function AnnotationsList({ reconstructionId, annotations }: AnnotationsListProps) {
  const queryClient = useQueryClient()
  const deleteAnnotation = useMutation({
    mutationFn: (id: number) =>
      del(`/reconstruction/${reconstructionId}/annotations/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['annotations', reconstructionId] }),
  })

  if (!annotations.length) return null

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>
        Annotations ({annotations.length})
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {annotations.map((ann) => (
          <div
            key={ann.id}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '3px 6px', borderRadius: 4,
              border: '1px solid var(--border)', background: 'var(--bg)',
            }}
          >
            <span
              style={{
                width: 8, height: 8, borderRadius: 2,
                background: ann.color, flexShrink: 0,
              }}
            />
            <span style={{ flex: 1, fontSize: 10, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {ann.label}
            </span>
            <button
              onClick={() => deleteAnnotation.mutate(ann.id)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--text-muted)', fontSize: 11, padding: '0 2px', lineHeight: 1,
              }}
              title="Delete annotation"
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <a
        href={`${BASE_URL}/reconstruction/${reconstructionId}/annotations.geojson`}
        download={`annotations_${reconstructionId}.geojson`}
        style={{
          display: 'block', marginTop: 6, fontSize: 10,
          color: '#58a6ff', textDecoration: 'none',
        }}
      >
        ↓ Export GeoJSON
      </a>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main tab
// ---------------------------------------------------------------------------

export default function SplatViewerTab() {
  const { selectedSessionId, targetSessionId, setTargetSessionId, splitPaneActive, toggleSplitPane } = useMapStore()
  const { data: allJobs, isLoading } = useAllJobsForSession(selectedSessionId)
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [showCoverageGaps, setShowCoverageGaps] = useState(false)
  const [activeTool, setActiveTool] = useState<ActiveTool>('none')
  const [measurePoints, setMeasurePoints] = useState<MeasurePoint[]>([])
  const [measureMode, setMeasureMode] = useState<'measure-dist' | 'measure-area' | null>(null)

  const jobs = allJobs ?? []
  const running = jobs.filter((j) => ACTIVE_STATUSES.includes(j.status))
  const completed = jobs.filter((j) => j.status === 'complete')
  const activeId = selectedJobId ?? completed[0]?.id ?? null
  const { data: reconstructionDetails } = useReconstructionDetails(activeId)
  const { data: geoTransform } = useGeoTransform(activeId)
  const selectedJobComplete = completed.some((j) => j.id === activeId)
  const { data: coverageGaps, isFetching: gapsFetching } = useCoverageGaps(
    activeId,
    selectedJobComplete ?? false,
  )
  const { data: annotations = [] } = useAnnotations(activeId)

  const geoAvailable = !!geoTransform && geoTransform.utm_zone !== 'unknown'

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

  // Reset tool and measurements when switching reconstructions
  useEffect(() => {
    setActiveTool('none')
    setMeasurePoints([])
    setMeasureMode(null)
  }, [activeId])

  function handleMeasurePoint(pt: MeasurePoint) {
    setMeasurePoints((prev) => {
      const next = [...prev, pt]
      if (activeTool === 'measure-dist' && next.length >= 2) {
        setMeasureMode('measure-dist')
        setActiveTool('none')
        return next.slice(0, 2)
      }
      if (activeTool === 'measure-area') setMeasureMode('measure-area')
      return next
    })
  }

  function handleMeasureClose() {
    setMeasureMode('measure-area')
    setActiveTool('none')
  }

  function handleClearMeasure() {
    setMeasurePoints([])
    setMeasureMode(null)
  }

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

        {activeId !== null && selectedJobComplete && (
          <>
            <ViewerToolbar
              activeTool={activeTool}
              onToolChange={(tool) => { setActiveTool(tool); if (tool !== 'measure-dist' && tool !== 'measure-area') { setMeasurePoints([]); setMeasureMode(null) } }}
              geoTransformAvailable={geoAvailable}
              hasMeasurePoints={measurePoints.length > 0}
              onClearMeasure={handleClearMeasure}
            />
            <button
              onClick={toggleSplitPane}
              style={{
                padding: '4px 8px', borderRadius: 4, fontSize: 11, marginTop: 4,
                border: splitPaneActive ? '1px solid #0ea5e9' : '1px solid var(--border)',
                background: splitPaneActive ? 'rgba(14,165,233,0.15)' : 'var(--bg)',
                color: splitPaneActive ? '#38bdf8' : 'var(--text-muted)',
                cursor: 'pointer', fontFamily: 'inherit', width: '100%', textAlign: 'left',
              }}
            >
              {splitPaneActive ? '⊟ Full 3D' : '⊞ Split View'}
            </button>
            <a
              href={`${BASE_URL}/reconstruction/${activeId}/pointcloud`}
              download={`pointcloud_${activeId}.las`}
              style={{
                display: 'block',
                padding: '4px 8px',
                borderRadius: 4,
                fontSize: 11,
                marginTop: 4,
                border: '1px solid rgba(88,166,255,0.3)',
                background: 'rgba(88,166,255,0.1)',
                color: '#58a6ff',
                textDecoration: 'none',
              }}
            >
              Download LAS
            </a>
          </>
        )}

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

        {activeId !== null && (
          <AnnotationsList reconstructionId={activeId} annotations={annotations} />
        )}
      </div>

      {/* Viewer */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'row', background: '#0a0a0a', overflow: 'hidden' }}>
        {splitPaneActive && activeId !== null && <MiniLeafletPane />}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          {activeId !== null ? (
            <SplatCanvas
              key={activeId}
              reconstructionId={activeId}
              coverageGaps={coverageGaps ?? null}
              showCoverageGaps={showCoverageGaps}
              activeTool={activeTool}
              geoTransform={geoTransform}
              annotations={annotations}
              onAnnotationCreated={() => setActiveTool('none')}
              measurePoints={measurePoints}
              measureMode={measureMode}
              onMeasurePoint={handleMeasurePoint}
              onMeasureClose={handleMeasureClose}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
              {running.length > 0 ? 'Reconstruction in progress…' : 'Select a reconstruction'}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
