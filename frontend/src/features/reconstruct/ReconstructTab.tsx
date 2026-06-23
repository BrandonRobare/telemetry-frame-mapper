import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post } from '../../shared/api/client'
import {
  isLiveReconstructionStatus,
  useReconstructionStatusEvents,
} from '../../shared/api/reconstructionStatusEvents'
import { useMapStore } from '../../shared/stores/mapStore'
import { useToast } from '../../shared/hooks/useToast'
import { Button } from '../../shared/components/Button'
import { formatEta } from '../../shared/time'
import type { Job } from '../../types/api'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

interface TargetAreaOption { id: number; name: string }

// ---- hooks ----

function useJobs(sseConnectedIds: ReadonlySet<number>) {
  return useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: () => get<Job[]>('/jobs/'),
    refetchInterval: (query) => {
      const jobs = query.state.data ?? []
      const needsPollingFallback = jobs.some((j) =>
        isLiveReconstructionStatus(j.status) && !sseConnectedIds.has(j.id)
      )
      return needsPollingFallback ? 3000 : false
    },
  })
}

function useTargetAreas() {
  return useQuery<TargetAreaOption[]>({
    queryKey: ['target-areas'],
    queryFn: () => get<TargetAreaOption[]>('/target-areas/'),
  })
}

function useFrameSelection(sessionId: number | null) {
  return useQuery<{ image_ids: number[] }>({
    queryKey: ['frame-selection', sessionId],
    queryFn: () => get(`/reconstruction/frame-selection/${sessionId}`),
    enabled: sessionId !== null,
  })
}

// ---- helpers ----

function formatDuration(start: string, end: string | null): string {
  const startMs = new Date(start).getTime()
  const endMs = end ? new Date(end).getTime() : Date.now()
  const sec = Math.round((endMs - startMs) / 1000)
  if (sec < 60) return `${sec}s`
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
}

const STATUS_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  pending:        { bg: 'var(--tan-soft)',     text: 'var(--tan-text)',      label: 'Pending' },
  running_colmap: { bg: 'var(--warning-soft)', text: 'var(--warning)',       label: 'COLMAP' },
  running_gsplat: { bg: 'var(--accent-soft)',  text: 'var(--accent-strong)', label: 'Gaussian' },
  complete:       { bg: 'var(--success-soft)', text: 'var(--success)',       label: 'Complete' },
  failed:         { bg: 'var(--danger-soft)',  text: 'var(--danger)',        label: 'Failed' },
}

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_BADGE[status] ?? { bg: 'var(--surface-2)', text: 'var(--text)', label: status }
  return (
    <span
      className="text-xs rounded"
      style={{ padding: '2px 8px', background: s.bg, color: s.text, whiteSpace: 'nowrap' }}
    >
      {s.label}
    </span>
  )
}

// ---- main component ----

export default function ReconstructTab() {
  const { selectedSessionId } = useMapStore()
  const { addToast } = useToast()
  const qc = useQueryClient()

  const [preset, setPreset] = useState<'quick' | 'full'>('quick')
  const [targetAreaId, setTargetAreaId] = useState<number | null>(null)
  const [sseConnectedIds, setSseConnectedIds] = useState<ReadonlySet<number>>(new Set())

  const { data: allJobs } = useJobs(sseConnectedIds)
  const { data: targetAreas } = useTargetAreas()
  const { data: frameSelection } = useFrameSelection(selectedSessionId)
  useReconstructionStatusEvents(allJobs, setSseConnectedIds)

  const sessionJobs = (allJobs ?? []).filter((j) => j.session_id === selectedSessionId)
  const activeJob = sessionJobs.find((j) => isLiveReconstructionStatus(j.status))
  const selectedCount = frameSelection?.image_ids.length ?? 0
  const activeEta = activeJob ? formatEta(activeJob.started_at, activeJob.progress_pct) : null

  const startMutation = useMutation({
    mutationFn: () =>
      post<{ id: number; status: string }>('/reconstruction/start', {
        session_id: selectedSessionId,
        preset,
        ...(targetAreaId != null ? { target_area_id: targetAreaId } : {}),
      }),
    onSuccess: () => {
      addToast('Reconstruction started', 'success')
      qc.invalidateQueries({ queryKey: ['jobs'] })
    },
    onError: (err: Error) =>
      addToast(err.message || 'Failed to start reconstruction', 'error'),
  })

  const cancelMutation = useMutation({
    mutationFn: (id: number) =>
      fetch(`${BASE_URL}/reconstruction/${id}/cancel`, { method: 'POST' }),
    onSuccess: () => {
      addToast('Reconstruction cancelled', 'info')
      qc.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  if (selectedSessionId === null) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        Select a session first
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-6" style={{ color: 'var(--text)' }}>
      <div className="mx-auto flex flex-col gap-6" style={{ maxWidth: 720 }}>

        {/* ---- Start card ---- */}
        <section
          className="rounded-lg p-5 flex flex-col gap-4"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <h2 className="text-base font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
            Start Reconstruction
          </h2>

          {selectedCount > 0 && (
            <p className="text-xs" style={{ color: 'var(--accent-strong)', margin: 0 }}>
              {selectedCount} frames manually selected (Review tab). Only these frames will be used.
            </p>
          )}

          {/* Preset */}
          <div className="flex gap-6">
            {(['quick', 'full'] as const).map((p) => (
              <label key={p} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13 }}>
                <input
                  type="radio"
                  name="preset"
                  value={p}
                  checked={preset === p}
                  onChange={() => setPreset(p)}
                  style={{ accentColor: 'var(--accent)' }}
                />
                <span style={{ color: preset === p ? 'var(--text)' : 'var(--text-muted)' }}>
                  {p === 'quick' ? 'Quick — fewer iterations, faster' : 'Full — best quality, slower'}
                </span>
              </label>
            ))}
          </div>

          {/* Target area */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Target area (optional — crops images to polygon before COLMAP)
            </label>
            <select
              value={targetAreaId ?? ''}
              onChange={(e) => setTargetAreaId(e.target.value ? Number(e.target.value) : null)}
              style={{
                background: 'var(--surface-2)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)', padding: '5px 8px', color: 'var(--text)',
                fontSize: 13, fontFamily: 'inherit', maxWidth: 280,
              }}
            >
              <option value="">No crop — use all usable frames</option>
              {(targetAreas ?? []).map((ta) => (
                <option key={ta.id} value={ta.id}>{ta.name}</option>
              ))}
            </select>
          </div>

          <Button
            variant="primary"
            disabled={!!activeJob || startMutation.isPending}
            onClick={() => startMutation.mutate()}
            style={{ alignSelf: 'flex-start' }}
          >
            {startMutation.isPending
              ? 'Starting…'
              : activeJob
              ? 'Reconstruction already in progress'
              : 'Start Reconstruction'}
          </Button>
        </section>

        {/* ---- Active job progress ---- */}
        {activeJob && (
          <section
            className="rounded-lg p-5 flex flex-col gap-3"
            style={{ background: 'var(--surface)', border: '1px solid var(--accent)' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h2 className="text-base font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
                Reconstruction #{activeJob.id} — In Progress
              </h2>
              <button
                onClick={() => cancelMutation.mutate(activeJob.id)}
                disabled={cancelMutation.isPending}
                style={{
                  background: 'none', border: '1px solid var(--danger)',
                  borderRadius: 4, padding: '3px 10px', fontSize: 12,
                  color: 'var(--danger, #f85149)', cursor: 'pointer', fontFamily: 'inherit',
                }}
              >
                {cancelMutation.isPending ? 'Cancelling…' : 'Cancel'}
              </button>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <StatusBadge status={activeJob.status} />
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                {activeJob.step || 'Initializing…'}
              </span>
            </div>

            <div style={{ height: 6, borderRadius: 3, background: 'var(--surface-2)', overflow: 'hidden' }}>
              <div
                style={{
                  height: '100%', borderRadius: 3,
                  background: 'var(--accent)',
                  width: `${activeJob.progress_pct}%`,
                  transition: 'width 0.5s ease',
                }}
              />
            </div>

            <p className="text-xs" style={{ color: 'var(--text-muted)', margin: 0 }}>
              {activeJob.progress_pct.toFixed(1)}%
              {' · '}{activeJob.frames_used} frames
              {activeJob.started_at && ` · elapsed ${formatDuration(activeJob.started_at, null)}`}
              {activeEta && ` · ${activeEta}`}
            </p>
          </section>
        )}

        {/* ---- History ---- */}
        {sessionJobs.length > 0 && (
          <section
            className="rounded-lg p-5 flex flex-col gap-3"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
          >
            <h2 className="text-base font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
              History
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {sessionJobs.map((job) => (
                <div
                  key={job.id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    background: 'var(--surface-2)', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-md)', padding: '10px 12px',
                  }}
                >
                  <span className="text-xs" style={{ color: 'var(--text-muted)', minWidth: 28 }}>
                    #{job.id}
                  </span>
                  <StatusBadge status={job.status} />
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    {job.preset} · {job.frames_used} frames
                  </span>
                  {job.started_at && (
                    <span className="text-xs" style={{ color: 'var(--text-muted)', marginLeft: 'auto' }}>
                      {formatDuration(job.started_at, job.completed_at)}
                    </span>
                  )}
                  {job.status === 'complete' && (
                    <a
                      href={`${BASE_URL}/reconstruction/${job.id}/splat?lod=full`}
                      download={`splat_${job.id}.ply`}
                      style={{
                        padding: '3px 10px', borderRadius: 'var(--radius-sm)', fontSize: 12,
                        background: 'var(--accent-soft)',
                        border: '1px solid var(--accent-soft)',
                        color: 'var(--accent-strong)', textDecoration: 'none', whiteSpace: 'nowrap',
                      }}
                    >
                      ↓ Download .ply
                    </a>
                  )}
                  {job.status === 'failed' && job.error_msg && (
                    <span className="text-xs" style={{ color: 'var(--danger, #f85149)', marginLeft: 'auto' }}>
                      {job.error_msg}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {sessionJobs.length === 0 && !activeJob && (
          <p className="text-sm" style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem 0' }}>
            No reconstructions for this session yet.
          </p>
        )}
      </div>
    </div>
  )
}
