import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiUrl, get, post, del } from '../../shared/api/client'
import { isLiveReconstructionStatus } from '../../shared/api/reconstructionStatusEvents'
import { useMapStore } from '../../shared/stores/mapStore'
import { Skeleton } from '../../shared/components/Skeleton'
import EmptyState from '../../shared/components/EmptyState'
import { easeOut } from '../../shared/motion'
import type {
  Job,
  GeoTransform,
  Reconstruction,
  TrainingMetricPoint,
  CoverageGapCell,
  Annotation,
  FlythroughStatus,
  SemanticStatus,
  SemanticSummary,
  SystemResources,
  SemanticClassName,
} from '../../types/api'
import { SEMANTIC_CLASS_COLORS } from '../../types/api'
import { deriveGroundPlaneY, geoOriginLatLon, gpsToWorld, worldToGps, useRayCast } from './useViewerCoords'
import { smoothstep } from './smoothstep'
import { cleanupFlythroughRecording } from './flythroughRecording'
import MiniLeafletPane from './MiniLeafletPane'
import { resolveActiveJobId } from './activeJob'
import { sampleProfile, computeVolume } from './measurementMath'
import type { ProfileSample } from './measurementMath'
import type { VolumeResult } from './measurementMath'
import ProfilePanel from './ProfilePanel'
import VolumePanel from './VolumePanel'
import {
  cycleSpeed,
  interpolateKeyframes,
  scaledSegmentDurationMs,
  selectNarrationCallout,
  stepKeyframeIndex,
  type NarrationPoint,
} from './presentationMode'


// Radius (world units, ~meters) within which a flown-through camera position
// triggers an annotation's narration callout during presentation mode.
const NARRATION_ENTER_RADIUS_M = 6

const SEMANTIC_CLASS_NAMES: SemanticClassName[] = ['ground', 'vegetation', 'structure', 'vehicle', 'water', 'other']

interface SemanticOverlayPoint {
  x: number
  y: number
  z: number
  label: number
}

interface SemanticOverlay {
  points: SemanticOverlayPoint[]
}

type ActiveTool = 'none' | 'annotate' | 'measure-dist' | 'measure-area' | 'measure-profile' | 'measure-volume'

interface MeasurePoint {
  worldPos: { x: number; y: number; z: number }
  gps: { lat: number; lon: number; alt: number } | null
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
      const hasRunning = jobs.some((j) => isLiveReconstructionStatus(j.status))
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


function parseSemanticOverlay(buffer: ArrayBuffer): SemanticOverlay {
  const view = new DataView(buffer)
  const count = view.getUint32(0, true)
  const xyzOffset = 4
  const labelOffset = xyzOffset + count * 3 * 4
  const points: SemanticOverlayPoint[] = []
  for (let i = 0; i < count; i += 1) {
    const base = xyzOffset + i * 12
    points.push({
      x: view.getFloat32(base, true),
      y: view.getFloat32(base + 4, true),
      z: view.getFloat32(base + 8, true),
      label: view.getUint8(labelOffset + i),
    })
  }
  return { points }
}

function useSystemResources() {
  return useQuery<SystemResources>({
    queryKey: ['system-resources'],
    queryFn: () => get<SystemResources>('/system/resources'),
    staleTime: 30_000,
  })
}

function useSemanticStatus(reconstructionId: number | null) {
  return useQuery<SemanticStatus>({
    queryKey: ['semantic-status', reconstructionId],
    queryFn: () => get<SemanticStatus>(`/reconstruction/${reconstructionId!}/semantic-labels/status`),
    enabled: reconstructionId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.semantic_status
      return status === 'pending' || status === 'running' ? 2000 : false
    },
  })
}

function useSemanticSummary(reconstructionId: number | null, enabled: boolean) {
  return useQuery<SemanticSummary>({
    queryKey: ['semantic-summary', reconstructionId, 'preview'],
    queryFn: () => get<SemanticSummary>(`/reconstruction/${reconstructionId!}/semantic-labels?lod=preview`),
    enabled: reconstructionId !== null && enabled,
    retry: false,
  })
}

function useSemanticOverlay(reconstructionId: number | null, enabled: boolean) {
  return useQuery<SemanticOverlay>({
    queryKey: ['semantic-overlay', reconstructionId, 'preview'],
    queryFn: async () => {
      const res = await fetch(apiUrl(`/reconstruction/${reconstructionId!}/semantic-labels/overlay?lod=preview`), {
        credentials: 'include',
      })
      if (!res.ok) throw new Error(`Semantic overlay fetch failed: ${res.status}`)
      return parseSemanticOverlay(await res.arrayBuffer())
    },
    enabled: reconstructionId !== null && enabled,
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
  running_colmap: 'COLMAP: feature extraction & matching',
  running_gsplat: 'Gaussian Splatting',
}

function RunningCard({ job }: { job: Job }) {
  const label = STATUS_STEP_LABEL[job.status] ?? job.step
  const barColor = job.status === 'pending' ? 'var(--tan)' : 'var(--accent)'
  return (
    <div
      style={{
        padding: '10px 12px', borderRadius: 'var(--radius-md)',
        border: '1px solid var(--accent)',
        background: 'var(--accent-soft)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 6 }}>
        <span style={{ color: 'var(--text)', fontWeight: 600 }}>
          #{job.id} · {job.preset}
        </span>
        <span style={{ color: 'var(--accent-strong)' }}>{job.progress_pct.toFixed(0)}%</span>
      </div>
      <div style={{ height: 4, background: 'var(--surface-2)', borderRadius: 2, overflow: 'hidden' }}>
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
        marginTop: 8, padding: '6px 8px', borderRadius: 'var(--radius-sm)',
        background: 'var(--surface-2)', fontSize: 10, color: 'var(--text-muted)',
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
        marginTop: 8, padding: '6px 8px', borderRadius: 'var(--radius-sm)',
        background: 'var(--surface-2)', border: '1px solid var(--border)',
      }}
    >
      <div style={{ fontWeight: 600, color: 'var(--text)', marginBottom: 6, fontSize: 10 }}>
        Training Quality
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 2 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 8 }}>PSNR</span>
            <span style={{ color: '#4F6349', fontSize: 9, fontWeight: 700 }}>
              {finalPsnr.toFixed(1)} dB
            </span>
          </div>
          <svg viewBox="0 0 72 28" style={{ width: '100%', height: 28, display: 'block' }}>
            {toPolyline(psnrVals, '#4F6349')}
          </svg>
          <div style={{ color: 'var(--text-muted)', fontSize: 7, textAlign: 'center' }}>pixel accuracy</div>
        </div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 2 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 8 }}>SSIM</span>
            <span style={{ color: '#9A5E32', fontSize: 9, fontWeight: 700 }}>
              {finalSsim.toFixed(2)}
            </span>
          </div>
          <svg viewBox="0 0 72 28" style={{ width: '100%', height: 28, display: 'block' }}>
            {toPolyline(ssimVals, '#9A5E32')}
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
        borderRadius: 2,
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
          background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 2,
          color: 'var(--text)', fontSize: 12, padding: '4px 6px', fontFamily: 'inherit',
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
            flex: 1, padding: '4px 0', borderRadius: 'var(--radius-sm)', border: 'none',
            background: label.trim() ? 'var(--accent-strong)' : 'var(--surface-2)',
            color: label.trim() ? 'var(--on-accent)' : 'var(--text-muted)',
            cursor: label.trim() ? 'pointer' : 'default',
            fontSize: 11, fontFamily: 'inherit',
          }}
        >
          Save
        </button>
        <button
          onClick={onCancel}
          style={{
            flex: 1, padding: '4px 0', borderRadius: 2,
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

function useMeasurementLayer({ viewerRef, viewerReady, points, mode }: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  viewerRef: React.RefObject<any>
  viewerReady: boolean
  points: MeasurePoint[]
  mode: 'measure-dist' | 'measure-area' | 'measure-profile' | 'measure-volume' | null
}) {
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
        const first = points[0]
        const last = points[points.length - 1]
        if (first.gps && last.gps) {
          const distance = await import('@turf/distance').then(({ default: turfDist }) =>
            turfDist(
              [first.gps!.lon, first.gps!.lat],
              [last.gps!.lon, last.gps!.lat],
              { units: 'meters' },
            )
          )
          labelText = distance >= 1000 ? `${(distance / 1000).toFixed(2)} km` : `${distance.toFixed(1)} m`
        } else {
          const dx = last.worldPos.x - first.worldPos.x
          const dy = last.worldPos.y - first.worldPos.y
          const dz = last.worldPos.z - first.worldPos.z
          const distance = Math.sqrt(dx * dx + dy * dy + dz * dz)
          labelText = `${distance.toFixed(1)} scene units ⚠`
        }
      } else if (mode === 'measure-area' && points.length >= 3) {
        if (points.every((point) => point.gps)) {
          const area = await import('@turf/area').then(({ default: turfArea }) => {
            const coords = [...points.map((p): [number, number] => [p.gps!.lon, p.gps!.lat])]
            coords.push(coords[0])
            return turfArea({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] }, properties: {} })
          })
          labelText = area >= 10000 ? `${(area / 10000).toFixed(2)} ha` : `${area.toFixed(0)} m²`
        } else {
          let doubleArea = 0
          for (let i = 0; i < points.length; i += 1) {
            const current = points[i].worldPos
            const next = points[(i + 1) % points.length].worldPos
            doubleArea += current.x * next.z - next.x * current.z
          }
          labelText = `${(Math.abs(doubleArea) / 2).toFixed(0)} scene units² ⚠`
        }
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
  onPresent: () => void
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
  onPresent,
}: FlythroughControlsProps) {
  const canRun = keyframeCount >= 2 && !recording
  const serverRunning = status?.flythrough_status === 'pending' || status?.flythrough_status === 'running'
  // This panel floats over the always-dark 3D canvas, so it uses an explicit
  // dark-warm surface with light text rather than the light theme tokens.
  const btnStyle = {
    padding: '4px 8px',
    borderRadius: 2,
    border: '1px solid rgba(255,255,255,0.18)',
    background: 'rgba(255,255,255,0.06)',
    color: '#D8D2C7',
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
        borderRadius: 'var(--radius-md)',
        background: 'rgba(28,27,25,0.9)',
        border: '1px solid rgba(255,255,255,0.14)',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ color: '#F2ECE0', fontSize: 11, fontWeight: 700 }}>Flythrough</span>
        <span style={{ color: '#B9B2A6', fontSize: 10 }}>{keyframeCount} keyframes</span>
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
        <button
          type="button"
          onClick={onPresent}
          disabled={!canRun}
          title={canRun ? 'Enter presentation mode' : 'Add at least two keyframes to present'}
          style={{
            ...btnStyle,
            opacity: canRun ? 1 : 0.5,
            border: '1px solid rgba(226,168,119,0.5)',
            background: 'rgba(226,168,119,0.14)',
            color: '#E2A877',
            fontWeight: 600,
          }}
        >
          ▶ Present
        </button>
      </div>
      {message && (
        <p style={{ margin: 0, color: '#B9B2A6', fontSize: 10 }}>{message}</p>
      )}
      {status?.flythrough_status === 'failed' && status.flythrough_error && (
        <p style={{ margin: 0, color: '#F0A18C', fontSize: 10 }}>
          {status.flythrough_error}
        </p>
      )}
      {status?.flythrough_status === 'complete' && status.flythrough_path && (
        <a
          href={apiUrl(`/reconstruction/${reconstructionId}/flythrough`)}
          download={`flythrough_${reconstructionId}.mp4`}
          style={{ color: '#E2A877', fontSize: 11, textDecoration: 'none' }}
        >
          Download server MP4
        </a>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Presentation mode overlay — playback controls + narration callout
// ---------------------------------------------------------------------------

interface PresentationCallout {
  id: number
  label: string
  color: string
}

interface PresentationOverlayProps {
  keyframeIndex: number
  keyframeCount: number
  paused: boolean
  speed: number
  callout: PresentationCallout | null
  onTogglePause: () => void
  onPrev: () => void
  onNext: () => void
  onSpeedChange: (direction: 1 | -1) => void
  onExit: () => void
}

function PresentationOverlay({
  keyframeIndex,
  keyframeCount,
  paused,
  speed,
  callout,
  onTogglePause,
  onPrev,
  onNext,
  onSpeedChange,
  onExit,
}: PresentationOverlayProps) {
  const btnStyle = {
    padding: '4px 8px',
    borderRadius: 2,
    border: '1px solid rgba(255,255,255,0.18)',
    background: 'rgba(255,255,255,0.06)',
    color: '#D8D2C7',
    cursor: 'pointer',
    fontSize: 11,
    fontFamily: 'inherit',
  }

  return (
    <>
      <div
        style={{
          position: 'absolute',
          right: 12,
          top: 12,
          zIndex: 20,
          padding: 10,
          borderRadius: 'var(--radius-md)',
          background: 'rgba(28,27,25,0.9)',
          border: '1px solid rgba(255,255,255,0.14)',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 }}>
          <span style={{ color: '#F2ECE0', fontSize: 11, fontWeight: 700 }}>Presenting</span>
          <span style={{ color: '#B9B2A6', fontSize: 10 }}>
            {Math.min(keyframeIndex + 1, keyframeCount)} / {keyframeCount}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <button type="button" onClick={onPrev} style={btnStyle} title="Previous keyframe (←)">⏮</button>
          <button type="button" onClick={onTogglePause} style={btnStyle} title="Play/pause (space)">
            {paused ? '▶ Play' : '⏸ Pause'}
          </button>
          <button type="button" onClick={onNext} style={btnStyle} title="Next keyframe (→)">⏭</button>
          <button type="button" onClick={() => onSpeedChange(1)} style={btnStyle} title="Cycle playback speed">
            {speed}×
          </button>
        </div>
        <button
          type="button"
          onClick={onExit}
          style={{ ...btnStyle, textAlign: 'center' }}
          title="Exit presentation (Esc)"
        >
          ✕ Exit
        </button>
      </div>
      <AnimatePresence>
        {callout && (
          <motion.div
            key={callout.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            transition={{ duration: 0.25, ease: easeOut }}
            style={{
              position: 'absolute',
              left: '50%',
              bottom: 28,
              transform: 'translateX(-50%)',
              zIndex: 20,
              maxWidth: 420,
              padding: '10px 18px',
              borderRadius: 'var(--radius-md)',
              background: 'rgba(28,27,25,0.92)',
              border: `1px solid ${callout.color}`,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <span style={{ width: 10, height: 10, borderRadius: 2, background: callout.color, flexShrink: 0 }} />
            <span style={{ color: '#F2ECE0', fontSize: 13, fontWeight: 600 }}>{callout.label}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </>
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
  semanticOverlay: SemanticOverlay | null
  visibleSemanticClasses: Set<number>
  showSemanticOverlay: boolean
  activeTool: ActiveTool
  geoTransform: GeoTransform | undefined
  annotations: Annotation[]
  onAnnotationCreated: () => void
  measurePoints: MeasurePoint[]
  measureMode: 'measure-dist' | 'measure-area' | 'measure-profile' | 'measure-volume' | null
  onMeasurePoint: (pt: MeasurePoint) => void
  onMeasureClose: () => void
  presenting: boolean
  onEnterPresentation: () => void
  onExitPresentation: () => void
}

function SplatCanvas({
  reconstructionId,
  coverageGaps,
  showCoverageGaps,
  semanticOverlay,
  visibleSemanticClasses,
  showSemanticOverlay,
  activeTool,
  geoTransform,
  annotations,
  onAnnotationCreated,
  measurePoints,
  measureMode,
  onMeasurePoint,
  onMeasureClose,
  presenting,
  onEnterPresentation,
  onExitPresentation,
}: SplatCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<unknown>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const gapGroupRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const semanticGroupRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const annotationGroupRef = useRef<any>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const rafRef = useRef<number | null>(null)
  const presentationRafRef = useRef<number | null>(null)
  const presentationStateRef = useRef({ segment: 0, elapsedInSegment: 0, paused: false, speed: 1 })
  const activeCalloutIdRef = useRef<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [viewerReady, setViewerReady] = useState(false)
  const [pendingAnnotation, setPendingAnnotation] = useState<PendingAnnotation | null>(null)
  const [flythroughKeyframes, setFlythroughKeyframes] = useState<FlythroughKeyframe[]>([])
  const [recording, setRecording] = useState(false)
  const [flythroughMessage, setFlythroughMessage] = useState<string | null>(null)
  const [presentationDisplay, setPresentationDisplay] = useState<{
    keyframeIndex: number
    paused: boolean
    speed: number
    callout: PresentationCallout | null
  }>({ keyframeIndex: 0, paused: false, speed: 1, callout: null })

  const queryClient = useQueryClient()
  const { data: flythroughStatus } = useFlythroughStatus(reconstructionId)
  const groundY = useMemo(() => deriveGroundPlaneY(geoTransform), [geoTransform])
  const calloutPoints = useMemo<(NarrationPoint & PresentationCallout)[]>(() => {
    if (!geoTransform) return []
    const points: (NarrationPoint & PresentationCallout)[] = []
    for (const ann of annotations) {
      const wp = gpsToWorld({ lat: ann.lat, lon: ann.lon, alt: ann.alt_m }, geoTransform)
      if (!wp) continue
      points.push({ id: ann.id, label: ann.label, color: ann.color, position: [wp.x, wp.y, wp.z] })
    }
    return points
  }, [annotations, geoTransform])
  const { castRay } = useRayCast(
    viewerRef as React.RefObject<unknown>,
    containerRef,
    groundY,
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
      rafRef.current = null

      function step(now: number) {
        const current = flythroughKeyframes[segment]
        const next = flythroughKeyframes[segment + 1]
        if (!current || !next) {
          resolve()
          return
        }
        if (startTime === null) startTime = now
        const durationMs = scaledSegmentDurationMs(next.duration_s, 1)
        const t = Math.min(1, (now - startTime) / durationMs)
        const ease = smoothstep(t)
        const { position, target } = interpolateKeyframes(current, next, ease)
        camera.position.set(position[0], position[1], position[2])
        if (controls?.target?.set) controls.target.set(target[0], target[1], target[2])
        controls?.update?.()
        if (t < 1) {
          rafRef.current = window.requestAnimationFrame(step)
          return
        }
        segment += 1
        startTime = now
        if (segment >= flythroughKeyframes.length - 1) {
          rafRef.current = null
          resolve()
        } else {
          rafRef.current = window.requestAnimationFrame(step)
        }
      }

      rafRef.current = window.requestAnimationFrame(step)
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
    recorderRef.current = recorder
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data)
    }
    recorder.onstop = () => {
      downloadBlob(new Blob(chunks, { type: mimeType || 'video/webm' }), extension)
      stream.getTracks().forEach((track) => track.stop())
      if (recorderRef.current === recorder) recorderRef.current = null
      setRecording(false)
      setFlythroughMessage(`Downloaded ${extension.toUpperCase()} flythrough.`)
    }
    setRecording(true)
    setFlythroughMessage('Recording browser flythrough…')
    recorder.start()
    await previewFlythrough()
    if (recorderRef.current === recorder && recorder.state !== 'inactive') {
      recorder.stop()
    }
  }

  function enterPresentation() {
    if (flythroughKeyframes.length < 2) {
      setFlythroughMessage('Add at least two keyframes to present.')
      return
    }
    presentationStateRef.current = {
      segment: 0,
      elapsedInSegment: 0,
      paused: false,
      speed: presentationStateRef.current.speed || 1,
    }
    activeCalloutIdRef.current = null
    onEnterPresentation()
  }

  function jumpToKeyframe(direction: 1 | -1) {
    const state = presentationStateRef.current
    state.segment = stepKeyframeIndex(state.segment, direction, flythroughKeyframes.length)
    state.elapsedInSegment = 0
    state.paused = false
  }

  // Presentation playback — plays the same keyframe path as the flythrough
  // preview (interpolateKeyframes/scaledSegmentDurationMs from
  // presentationMode.ts), but supports pause/resume, adjustable speed, and
  // proximity-triggered annotation callouts. Mutable playback state lives in
  // presentationStateRef so keyboard/UI controls can steer it without
  // restarting this effect.
  useEffect(() => {
    if (!presenting) return
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const viewer = viewerRef.current as any
    const camera = viewer?.camera
    const controls = viewer?.orbitControls ?? viewer?.controls ?? null
    if (!camera || flythroughKeyframes.length < 2) {
      onExitPresentation()
      return
    }

    let lastFrameTime: number | null = null

    function frame(now: number) {
      const state = presentationStateRef.current
      if (lastFrameTime === null) lastFrameTime = now
      const delta = now - lastFrameTime
      lastFrameTime = now
      if (!state.paused) state.elapsedInSegment += delta

      const current = flythroughKeyframes[state.segment]
      const next = flythroughKeyframes[state.segment + 1]

      if (current && next) {
        const durationMs = scaledSegmentDurationMs(next.duration_s, state.speed)
        const t = Math.min(1, state.elapsedInSegment / durationMs)
        const ease = smoothstep(t)
        const { position, target } = interpolateKeyframes(current, next, ease)
        camera.position.set(position[0], position[1], position[2])
        if (controls?.target?.set) controls.target.set(target[0], target[1], target[2])
        controls?.update?.()

        if (t >= 1) {
          const advanced = stepKeyframeIndex(state.segment, 1, flythroughKeyframes.length)
          if (advanced === state.segment) {
            state.paused = true
          } else {
            state.segment = advanced
            state.elapsedInSegment = 0
          }
        }
      } else if (current) {
        camera.position.set(current.position[0], current.position[1], current.position[2])
        if (controls?.target?.set) controls.target.set(current.target[0], current.target[1], current.target[2])
        controls?.update?.()
        state.paused = true
      }

      const cameraPos: [number, number, number] = [camera.position.x, camera.position.y, camera.position.z]
      const callout = selectNarrationCallout(
        cameraPos,
        calloutPoints,
        activeCalloutIdRef.current,
        NARRATION_ENTER_RADIUS_M,
      )
      activeCalloutIdRef.current = callout?.id ?? null

      setPresentationDisplay({
        keyframeIndex: state.segment,
        paused: state.paused,
        speed: state.speed,
        callout: callout ? { id: callout.id, label: callout.label, color: callout.color } : null,
      })

      presentationRafRef.current = window.requestAnimationFrame(frame)
    }

    presentationRafRef.current = window.requestAnimationFrame(frame)
    return () => {
      if (presentationRafRef.current !== null) {
        window.cancelAnimationFrame(presentationRafRef.current)
        presentationRafRef.current = null
      }
    }
  }, [presenting, flythroughKeyframes, calloutPoints, onExitPresentation])

  // Keyboard controls for presentation mode: space = pause/resume,
  // arrows = prev/next keyframe, Esc = exit.
  useEffect(() => {
    if (!presenting) return

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault()
        presentationStateRef.current.paused = !presentationStateRef.current.paused
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        jumpToKeyframe(1)
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        jumpToKeyframe(-1)
      } else if (e.key === 'Escape') {
        e.preventDefault()
        onExitPresentation()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presenting, flythroughKeyframes.length, onExitPresentation])

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
          // SharedArrayBuffer needs cross-origin isolation (COOP/COEP headers) that
          // neither the Vite dev server nor typical static hosting provides — with
          // the default, addSplatScene never resolves and the viewer hangs on load.
          sharedMemoryForWorkers: false,
        })
        viewerRef.current = viewer

        const splatUrl = apiUrl(`/reconstruction/${reconstructionId}/splat?lod=preview`)
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
      cleanupFlythroughRecording({ rafRef, recorderRef })
      if (presentationRafRef.current !== null) {
        window.cancelAnimationFrame(presentationRafRef.current)
        presentationRafRef.current = null
      }
      setRecording(false)
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

  // Canvas click handler for all tools
  useEffect(() => {
    const container = containerRef.current
    if (!container || !viewerReady) return

    const measureTools: ActiveTool[] = ['measure-dist', 'measure-area', 'measure-profile', 'measure-volume']
    const isMeasure = measureTools.includes(activeTool)
    const isAnnotate = activeTool === 'annotate'

    if (!isAnnotate && !isMeasure) {
      container.style.cursor = ''
      return
    }

    container.style.cursor = 'crosshair'

    function handleClick(e: MouseEvent) {
      if (isAnnotate) {
        castRay(e).then((result) => {
          if (result) setPendingAnnotation(result)
        })
      } else if (isMeasure) {
        castRay(e).then((result) => {
          if (!result) return
          const gps = geoTransform ? worldToGps(result.worldPos, geoTransform) : null
          onMeasurePoint({ worldPos: result.worldPos, gps })
        })
      }
    }

    function handleDblClick(e: MouseEvent) {
      e.preventDefault()
      if (activeTool === 'measure-area' || activeTool === 'measure-profile' || activeTool === 'measure-volume') {
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


  // Semantic overlay point groups
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const viewer = viewerRef.current as any
    if (!viewer?.scene) return
    const scene = viewer.scene
    if (semanticGroupRef.current) {
      scene.remove(semanticGroupRef.current)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      semanticGroupRef.current.traverse((obj: any) => {
        if (obj.isPoints) { obj.geometry.dispose(); obj.material.dispose() }
      })
      semanticGroupRef.current = null
    }
    if (!semanticOverlay || !showSemanticOverlay || semanticOverlay.points.length === 0) return
    let cancelled = false
    import('three').then((THREE) => {
      if (cancelled) return
      const group = new THREE.Group()
      for (const [classIndex, className] of SEMANTIC_CLASS_NAMES.entries()) {
        if (!visibleSemanticClasses.has(classIndex)) continue
        const points = semanticOverlay.points.filter((pt) => pt.label === classIndex)
        if (points.length === 0) continue
        const positions = new Float32Array(points.length * 3)
        points.forEach((pt, idx) => {
          positions[idx * 3] = pt.x
          positions[idx * 3 + 1] = pt.y
          positions[idx * 3 + 2] = pt.z
        })
        const geo = new THREE.BufferGeometry()
        geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
        const mat = new THREE.PointsMaterial({
          color: SEMANTIC_CLASS_COLORS[className],
          size: 0.05,
          transparent: true,
          opacity: 0.88,
          depthWrite: false,
        })
        const cloud = new THREE.Points(geo, mat)
        group.add(cloud)
      }
      scene.add(group)
      semanticGroupRef.current = group
    })
    return () => {
      cancelled = true
      if (semanticGroupRef.current) {
        scene.remove(semanticGroupRef.current)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        semanticGroupRef.current.traverse((obj: any) => {
          if (obj.isPoints) { obj.geometry.dispose(); obj.material.dispose() }
        })
        semanticGroupRef.current = null
      }
    }
  }, [semanticOverlay, showSemanticOverlay, visibleSemanticClasses, viewerReady])

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
          href={apiUrl(`/reconstruction/${reconstructionId}/splat?lod=full`)}
          download={`splat_${reconstructionId}.ply`}
          style={{ color: 'var(--accent-strong)', fontSize: 13 }}
        >
          Download .ply instead
        </a>
      </div>
    )
  }

  return (
    <div style={{ position: 'relative', flex: 1 }}>
      <AnimatePresence>
        {loading && (
          <motion.div
            initial={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.28, ease: easeOut }}
            style={{
              position: 'absolute', inset: 0, zIndex: 10,
              background: 'var(--surface)',
              display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', gap: 14, padding: 24,
            }}
          >
            <Skeleton width="70%" height={260} radius="var(--radius-lg)" style={{ maxWidth: 560 }} />
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Loading splat…</span>
          </motion.div>
        )}
      </AnimatePresence>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      {viewerReady && !presenting && (
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
          onPresent={enterPresentation}
        />
      )}
      {viewerReady && presenting && (
        <PresentationOverlay
          keyframeIndex={presentationDisplay.keyframeIndex}
          keyframeCount={flythroughKeyframes.length}
          paused={presentationDisplay.paused}
          speed={presentationDisplay.speed}
          callout={presentationDisplay.callout}
          onTogglePause={() => {
            presentationStateRef.current.paused = !presentationStateRef.current.paused
          }}
          onPrev={() => jumpToKeyframe(-1)}
          onNext={() => jumpToKeyframe(1)}
          onSpeedChange={(direction) => {
            presentationStateRef.current.speed = cycleSpeed(presentationStateRef.current.speed, direction)
          }}
          onExit={onExitPresentation}
        />
      )}
      {!presenting && pendingAnnotation && geoTransform && (
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
  function toolBtn(tool: ActiveTool, label: string, title: string, allowSceneUnits = false) {
    const active = activeTool === tool
    const enabled = geoTransformAvailable || allowSceneUnits
    return (
      <button
        key={tool}
        title={title}
        onClick={() => onToolChange(active ? 'none' : tool)}
        style={{
          padding: '4px 8px', borderRadius: 2, fontSize: 11,
          border: active ? '1px solid var(--accent)' : '1px solid var(--border)',
          background: active ? 'var(--accent-soft)' : 'var(--surface-2)',
          color: active ? 'var(--accent-strong)' : 'var(--text-muted)',
          cursor: enabled ? 'pointer' : 'not-allowed',
          fontFamily: 'inherit',
          opacity: enabled ? 1 : 0.5,
        }}
        disabled={!enabled}
      >
        {label}
      </button>
    )
  }

  const noGeoHelp = 'Geo-transform unavailable. Add GPS sync/GCPs for geographic output.'
  return (
    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 8 }}>
      {toolBtn('annotate', '⊕ Annotate', geoTransformAvailable ? 'Place GPS annotation' : noGeoHelp)}
      {toolBtn('measure-dist', '↔ Distance', geoTransformAvailable ? 'Measure distance between two points' : `${noGeoHelp} Measuring in scene units.`, true)}
      {toolBtn('measure-area', '⬡ Area', geoTransformAvailable ? 'Measure polygon area (double-click to close)' : `${noGeoHelp} Measuring in scene units.`, true)}
      {toolBtn('measure-profile', '〰 Profile', geoTransformAvailable ? 'Draw line for elevation profile (double-click to sample)' : `${noGeoHelp} Sampling in scene units.`, true)}
      {toolBtn('measure-volume', '◫ Volume', geoTransformAvailable ? 'Draw polygon for cut/fill volume (double-click to compute)' : `${noGeoHelp} Computing in scene units.`, true)}
      {hasMeasurePoints && (
        <button
          onClick={onClearMeasure}
          style={{
            padding: '4px 8px', borderRadius: 'var(--radius-sm)', fontSize: 11,
            border: '1px solid var(--border)', background: 'var(--surface-2)',
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
              padding: '3px 6px', borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)', background: 'var(--surface-2)',
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
        href={apiUrl(`/reconstruction/${reconstructionId}/annotations.geojson`)}
        download={`annotations_${reconstructionId}.geojson`}
        style={{
          display: 'block', marginTop: 6, fontSize: 10,
          color: 'var(--accent-strong)', textDecoration: 'none',
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
  const {
    selectedSessionId, targetSessionId, setTargetSessionId, targetReconstructionId,
    setTargetReconstructionId, splitPaneActive, toggleSplitPane, setRequestedTab,
  } = useMapStore()
  const { data: allJobs, isLoading } = useAllJobsForSession(selectedSessionId)
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [showCoverageGaps, setShowCoverageGaps] = useState(false)
  const [showSemanticOverlay, setShowSemanticOverlay] = useState(false)
  const [visibleSemanticClasses, setVisibleSemanticClasses] = useState<Set<number>>(
    () => new Set([0, 1, 2, 3, 4, 5]),
  )
  const [activeTool, setActiveTool] = useState<ActiveTool>('none')
  const [measurePoints, setMeasurePoints] = useState<MeasurePoint[]>([])
  const [measureMode, setMeasureMode] = useState<'measure-dist' | 'measure-area' | 'measure-profile' | 'measure-volume' | null>(null)
  const [profileSamples, setProfileSamples] = useState<ProfileSample[]>([])
  const [volumeResult, setVolumeResult] = useState<VolumeResult | null>(null)
  const [presenting, setPresenting] = useState(false)

  const jobs = allJobs ?? []
  const running = jobs.filter((j) => isLiveReconstructionStatus(j.status))
  const completed = jobs.filter((j) => j.status === 'complete')
  const activeId = resolveActiveJobId(selectedJobId, jobs, selectedSessionId)
  const { data: reconstructionDetails } = useReconstructionDetails(activeId)
  const { data: geoTransform } = useGeoTransform(activeId)
  const selectedJobComplete = completed.some((j) => j.id === activeId)
  const { data: coverageGaps, isFetching: gapsFetching } = useCoverageGaps(
    activeId,
    selectedJobComplete ?? false,
  )
  const { data: annotations = [] } = useAnnotations(activeId)
  const { data: systemResources } = useSystemResources()
  const { data: semanticStatus } = useSemanticStatus(activeId)
  const { data: semanticSummary } = useSemanticSummary(activeId, showSemanticOverlay)
  const { data: semanticOverlay } = useSemanticOverlay(activeId, showSemanticOverlay)
  const queryClient = useQueryClient()
  const semanticWorkflow = systemResources?.workflows.find((workflow) => workflow.key === 'semantic_labeling')
  const semanticAvailable = semanticWorkflow?.available ?? false
  const splitPaneCenter = useMemo(() => {
    const origin = geoOriginLatLon(geoTransform)
    return origin ? ([origin.lat, origin.lon] as [number, number]) : null
  }, [geoTransform])
  const semanticMutation = useMutation({
    mutationFn: () => post<SemanticStatus>(`/reconstruction/${activeId!}/semantic-labels`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['semantic-status', activeId] })
    },
  })

  const geoAvailable = !!geoTransform && geoTransform.utm_zone !== 'unknown'

  useEffect(() => {
    if (targetReconstructionId == null) return
    const match = (allJobs ?? []).find((job) => job.id === targetReconstructionId)
    if (match) {
      queueMicrotask(() => {
        setSelectedJobId(match.id)
        setTargetReconstructionId(null)
      })
    }
  }, [targetReconstructionId, allJobs, setTargetReconstructionId])

  useEffect(() => {
    if (targetSessionId == null) return
    const completedJobs = (allJobs ?? []).filter((j) => j.status === 'complete')
    const match = [...completedJobs]
      .sort((a, b) => b.id - a.id)
      .find((j) => j.session_id === targetSessionId)
    if (match) {
      queueMicrotask(() => {
        setSelectedJobId(match.id)
        setTargetSessionId(null)
      })
    }
  }, [targetSessionId, allJobs, setTargetSessionId])

  // Reset tool and measurements when switching reconstructions
  useEffect(() => {
    queueMicrotask(() => {
      setActiveTool('none')
      setMeasurePoints([])
      setMeasureMode(null)
      setProfileSamples([])
      setVolumeResult(null)
      setShowSemanticOverlay(false)
      setVisibleSemanticClasses(new Set([0, 1, 2, 3, 4, 5]))
      setPresenting(false)
    })
  }, [activeId])

  function enterPresentationMode() {
    // Presentation mode is a clean, chrome-free view of the flythrough — drop
    // out of any editing tool first so annotate/measure clicks don't fire
    // underneath it.
    setActiveTool('none')
    setMeasurePoints([])
    setMeasureMode(null)
    setPresenting(true)
  }

  function exitPresentationMode() {
    setPresenting(false)
  }

  function handleMeasurePoint(pt: MeasurePoint) {
    setMeasurePoints((prev) => {
      const next = [...prev, pt]
      if (activeTool === 'measure-dist' && next.length >= 2) {
        setMeasureMode('measure-dist')
        setActiveTool('none')
        return next.slice(0, 2)
      }
      if (activeTool === 'measure-area') setMeasureMode('measure-area')
      if (activeTool === 'measure-profile') setMeasureMode('measure-profile')
      if (activeTool === 'measure-volume') setMeasureMode('measure-volume')
      return next
    })
  }

  function handleMeasureClose() {
    if (measureMode === 'measure-profile' && measurePoints.length >= 2) {
      // Sample the profile along the polyline using the ground-plane Y
      const groundY = deriveGroundPlaneY(geoTransform ?? null)
      const sampler = () => groundY
      const samples = sampleProfile(
        measurePoints.map((p) => p.worldPos),
        sampler,
        0.5,
        geoTransform ?? undefined,
      )
      setProfileSamples(samples)
    }
    if (measureMode === 'measure-volume' && measurePoints.length >= 3) {
      const groundY = deriveGroundPlaneY(geoTransform ?? null)
      const sampler = () => groundY
      const vol = computeVolume(
        measurePoints.map((p) => p.worldPos),
        sampler,
        0, // reference = 0 in world space; extension point for different reference
        0.5,
      )
      setVolumeResult(vol)
    }
    if (measureMode === 'measure-area') {
      setMeasureMode('measure-area')
    }
    setActiveTool('none')
  }

  function handleClearMeasure() {
    setMeasurePoints([])
    setMeasureMode(null)
    setProfileSamples([])
    setVolumeResult(null)
  }

  if (selectedSessionId === null) {
    return (
      <EmptyState
        title="No session selected"
        description="Choose a session with a completed reconstruction to explore it in 3D."
        actionLabel="Open Overview"
        onAction={() => setRequestedTab('overview')}
      />
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
      {/* Sidebar — hidden in presentation mode for a clean, chrome-free view */}
      {!presenting && (
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
                  background: activeId === job.id ? 'var(--accent-soft)' : 'none',
                  border: activeId === job.id ? '1px solid var(--accent)' : '1px solid transparent',
                  borderRadius: 'var(--radius-md)', padding: '8px 10px', cursor: 'pointer',
                  textAlign: 'left', fontFamily: 'inherit',
                }}
              >
                <p className="text-xs font-medium" style={{ color: 'var(--text)', margin: '0 0 2px' }}>
                  #{job.id} · {job.preset}
                </p>
                <p className="text-xs" style={{ color: 'var(--text-muted)', margin: 0 }}>
                  {job.frames_used} frames
                </p>
              </button>
            ))}
          </>
        )}

        {activeId !== null && <GeoTransformPanel reconstructionId={activeId} />}

        {reconstructionDetails && (
          <p className="text-xs" style={{ color: 'var(--text-muted)', margin: '4px 0 2px' }}>
            {reconstructionDetails.frames_registered != null
              ? `${reconstructionDetails.frames_registered}/${reconstructionDetails.frames_used} frames registered`
              : `${reconstructionDetails.frames_used} frames`}
          </p>
        )}

        {activeId !== null && selectedJobComplete && (
          <>
            <ViewerToolbar
              activeTool={activeTool}
              onToolChange={(tool) => {
                setActiveTool(tool)
                const isMeasure = tool === 'measure-dist' || tool === 'measure-area' || tool === 'measure-profile' || tool === 'measure-volume'
                if (!isMeasure) {
                  setMeasurePoints([]); setMeasureMode(null); setProfileSamples([]); setVolumeResult(null)
                }
              }}
              geoTransformAvailable={geoAvailable}
              hasMeasurePoints={measurePoints.length > 0}
              onClearMeasure={handleClearMeasure}
            />
            <button
              onClick={toggleSplitPane}
              style={{
                padding: '4px 8px', borderRadius: 'var(--radius-sm)', fontSize: 11, marginTop: 4,
                border: splitPaneActive ? '1px solid var(--accent)' : '1px solid var(--border)',
                background: splitPaneActive ? 'var(--accent-soft)' : 'var(--surface-2)',
                color: splitPaneActive ? 'var(--accent-strong)' : 'var(--text-muted)',
                cursor: 'pointer', fontFamily: 'inherit', width: '100%', textAlign: 'left',
              }}
            >
              {splitPaneActive ? '⊟ Full 3D' : '⊞ Split View'}
            </button>
            <a
              href={apiUrl(`/reconstruction/${activeId}/pointcloud`)}
              download={`pointcloud_${activeId}.las`}
              style={{
                display: 'block',
                padding: '4px 8px',
                borderRadius: 'var(--radius-sm)',
                fontSize: 11,
                marginTop: 4,
                border: '1px solid var(--accent-soft)',
                background: 'var(--accent-soft)',
                color: 'var(--accent-strong)',
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
                borderRadius: 'var(--radius-sm)',
                border: showCoverageGaps ? '1px solid var(--danger-accent)' : '1px solid var(--border)',
                background: showCoverageGaps ? 'var(--danger-soft)' : 'var(--surface-2)',
                color: showCoverageGaps ? 'var(--danger)' : 'var(--text-muted)',
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

        {activeId !== null && selectedJobComplete && reconstructionDetails?.splat_path && (
          <div style={{ marginTop: 8 }}>
            <button
              onClick={() => {
                if (semanticStatus?.semantic_status === 'complete') {
                  setShowSemanticOverlay((v) => !v)
                } else {
                  semanticMutation.mutate()
                }
              }}
              disabled={!semanticAvailable || semanticMutation.isPending || semanticStatus?.semantic_status === 'pending' || semanticStatus?.semantic_status === 'running'}
              title={semanticAvailable ? 'Compute or show semantic labels' : `Semantic labeling unavailable: ${(semanticWorkflow?.missing ?? []).join(', ')}`}
              style={{
                width: '100%', padding: '4px 8px', borderRadius: 'var(--radius-sm)',
                border: showSemanticOverlay ? '1px solid var(--accent)' : '1px solid var(--border)',
                background: showSemanticOverlay ? 'var(--accent-soft)' : 'var(--surface-2)',
                color: showSemanticOverlay ? 'var(--accent-strong)' : 'var(--text-muted)',
                cursor: semanticAvailable ? 'pointer' : 'not-allowed', fontFamily: 'inherit', fontSize: 11,
                textAlign: 'left', opacity: semanticAvailable ? 1 : 0.55,
              }}
            >
              {semanticStatus?.semantic_status === 'pending' || semanticStatus?.semantic_status === 'running'
                ? '⟳ Semantic labels…'
                : semanticStatus?.semantic_status === 'complete'
                  ? showSemanticOverlay ? '◉ Semantic Labels' : '○ Semantic Labels'
                  : 'Compute semantic labels'}
            </button>
            {semanticStatus?.semantic_error && (
              <p style={{ color: 'var(--danger)', fontSize: 9, margin: '4px 0 0' }}>{semanticStatus.semantic_error}</p>
            )}
            {showSemanticOverlay && semanticSummary && (
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                {SEMANTIC_CLASS_NAMES.map((name, idx) => (
                  <button
                    key={name}
                    onClick={() => setVisibleSemanticClasses((prev) => {
                      const next = new Set(prev)
                      if (next.has(idx)) next.delete(idx); else next.add(idx)
                      return next
                    })}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 3, fontSize: 9,
                      border: '1px solid var(--border)', borderRadius: 2, padding: '2px 4px',
                      background: visibleSemanticClasses.has(idx) ? 'var(--surface-2)' : 'transparent',
                      color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'inherit',
                    }}
                  >
                    <span style={{ width: 7, height: 7, background: SEMANTIC_CLASS_COLORS[name], display: 'inline-block' }} />
                    {name} {semanticSummary.class_counts[name] ?? 0}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}


        {activeId !== null && (
          <AnnotationsList reconstructionId={activeId} annotations={annotations} />
        )}

        <ProfilePanel samples={profileSamples} onClear={handleClearMeasure} />

        {volumeResult && (
          <VolumePanel
            volume={volumeResult}
            referenceElevation={0}
            onClear={handleClearMeasure}
          />
        )}
      </div>
      )}

      {/* Viewer */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'row', background: '#0a0a0a', overflow: 'hidden' }}>
        {splitPaneActive && !presenting && activeId !== null && (
          <MiniLeafletPane center={splitPaneCenter} />
        )}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          {activeId !== null ? (
            <SplatCanvas
              key={activeId}
              reconstructionId={activeId}
              coverageGaps={coverageGaps ?? null}
              showCoverageGaps={showCoverageGaps}
              semanticOverlay={semanticOverlay ?? null}
              visibleSemanticClasses={visibleSemanticClasses}
              showSemanticOverlay={showSemanticOverlay}
              activeTool={activeTool}
              geoTransform={geoTransform}
              annotations={annotations}
              onAnnotationCreated={() => setActiveTool('none')}
              measurePoints={measurePoints}
              measureMode={measureMode}
              onMeasurePoint={handleMeasurePoint}
              onMeasureClose={handleMeasureClose}
              presenting={presenting}
              onEnterPresentation={enterPresentationMode}
              onExitPresentation={exitPresentationMode}
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
