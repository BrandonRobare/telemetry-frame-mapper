import { useState, type ComponentProps } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post } from '../../shared/api/client'
import {
  isLiveReconstructionStatus,
  useReconstructionStatusEvents,
} from '../../shared/api/reconstructionStatusEvents'
import { useMapStore } from '../../shared/stores/mapStore'
import { useToast } from '../../shared/hooks/useToast'
import { Button } from '../../shared/components/Button'
import { Badge } from '../../shared/components/Badge'
import TabHeader from '../../shared/components/TabHeader'
import EmptyState from '../../shared/components/EmptyState'
import { formatEta } from '../../shared/time'
import type {
  Job,
  PreflightQualityReport,
  QualityScorecard,
} from '../../types/api'
import { API_BASE_URL } from '../../shared/api/client'

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

function usePreflightReport(sessionId: number | null) {
  return useQuery<PreflightQualityReport>({
    queryKey: ['preflight-quality', sessionId],
    queryFn: () => get<PreflightQualityReport>(`/reconstruction/preflight/${sessionId}`),
    enabled: sessionId !== null,
  })
}

// ---- quality scorecard component ----

function QualityReportInline({ jobId }: { jobId: number }) {
  const [expanded, setExpanded] = useState(false)
  const { data, isLoading, isError } = useQuery<QualityScorecard>({
    queryKey: ['quality-scorecard', jobId],
    queryFn: () => get<QualityScorecard>(`/reconstruction/${jobId}/quality-scorecard`),
    enabled: expanded,
  })

  return (
    <div style={{ marginTop: 4 }}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-xs"
        style={{
          background: 'var(--surface-2)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)', padding: '3px 10px',
          color: 'var(--accent-strong)', cursor: 'pointer',
        }}
      >
        {expanded ? '▲ Hide report' : '▼ Quality report'}
      </button>
      {expanded && (
        <div
          className="flex flex-col gap-2 text-xs"
          style={{
            marginTop: 8, padding: 10,
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text-muted)',
          }}
        >
          {isLoading && <span>Loading…</span>}
          {isError && <span style={{ color: 'var(--danger)' }}>Failed to load report</span>}
          {data && (
            <>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                <span>Frames: {data.frame_counts.frames_registered}/{data.frame_counts.frames_used} ({data.frame_counts.registration_completeness_pct}% registered)</span>
                <span>Gaussians: {data.density.gaussian_count?.toLocaleString() ?? 'n/a'}</span>
                {data.reprojection_error.mean_px != null && (
                  <span>Reprojection: {data.reprojection_error.mean_px.toFixed(3)} px (σ={data.reprojection_error.std_px?.toFixed(3) ?? 'n/a'})</span>
                )}
                <span>PSNR: {data.quality.psnr_final?.toFixed(2) ?? 'n/a'} dB</span>
                <span>SSIM: {data.quality.ssim_final?.toFixed(4) ?? 'n/a'}</span>
                {data.quality.psnr_trend && (
                  <span>PSNR trend: {data.quality.psnr_trend.start.toFixed(1)} → {data.quality.psnr_trend.end.toFixed(1)} (+{data.quality.psnr_trend.delta.toFixed(1)})</span>
                )}
              </div>
              {data.coverage_gaps && (
                <div style={{ borderTop: '1px solid var(--border)', paddingTop: 6 }}>
                  <span>Coverage gaps: {data.coverage_gaps.total_gaps} cells</span>
                  {Object.keys(data.coverage_gaps.by_level).length > 0 && (
                    <span className="ml-2">
                      ({Object.entries(data.coverage_gaps.by_level).map(([k, v]) => `${k}: ${v}`).join(', ')})
                    </span>
                  )}
                </div>
              )}
              <a
                href={`${API_BASE_URL}/reconstruction/${jobId}/quality-scorecard`}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'var(--accent-strong)', textDecoration: 'underline', alignSelf: 'flex-start' }}
              >
                Export JSON
              </a>
            </>
          )}
        </div>
      )}
    </div>
  )
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
  cancelling:     { bg: 'var(--warning-soft)', text: 'var(--warning)',       label: 'Cancelling' },
  cancelled:      { bg: 'var(--surface-2)',    text: 'var(--text-muted)',    label: 'Cancelled' },
  complete:       { bg: 'var(--success-soft)', text: 'var(--success)',       label: 'Complete' },
  failed:         { bg: 'var(--danger-soft)',  text: 'var(--danger)',        label: 'Failed' },
}

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_BADGE[status] ?? { bg: 'var(--surface-2)', text: 'var(--text)', label: status }
  return (
    <Badge color={jobStatusBadgeColor(status)} className="rounded" style={{ padding: '2px 8px', whiteSpace: 'nowrap' }}>
      {s.label}
    </Badge>
  )
}

function jobStatusBadgeColor(status: string): ComponentProps<typeof Badge>['color'] {
  if (status === 'complete') return 'sage'
  if (status === 'failed') return 'red'
  if (status === 'pending') return 'tan'
  if (status === 'running_colmap') return 'amber'
  if (status === 'running_gsplat') return 'terracotta'
  if (status === 'cancelling') return 'amber'
  return 'muted'
}

// ---- main component ----

export default function ReconstructTab() {
  const { selectedSessionId, setRequestedTab } = useMapStore()
  const { addToast } = useToast()
  const qc = useQueryClient()

  const [preset, setPreset] = useState<'quick' | 'full'>('quick')
  const [targetAreaId, setTargetAreaId] = useState<number | null>(null)
  const [sseConnectedIds, setSseConnectedIds] = useState<ReadonlySet<number>>(new Set())

  const { data: allJobs } = useJobs(sseConnectedIds)
  const { data: targetAreas } = useTargetAreas()
  const { data: frameSelection } = useFrameSelection(selectedSessionId)
  const { data: preflightReport, isLoading: preflightLoading } = usePreflightReport(selectedSessionId)
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
      post(`/reconstruction/${id}/cancel`),
    onSuccess: () => {
      addToast('Cancellation requested', 'info')
      qc.invalidateQueries({ queryKey: ['jobs'] })
    },
    onError: (err: Error) =>
      addToast(err.message || 'Failed to cancel reconstruction', 'error'),
  })

  if (selectedSessionId === null) {
    return (
      <EmptyState
        title="No session selected"
        description="Choose a session to run COLMAP alignment and Gaussian-splat training."
        actionLabel="Open Overview"
        onAction={() => setRequestedTab('overview')}
      />
    )
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <TabHeader
        title="Reconstruct"
        description="Run COLMAP alignment and Gaussian-splat training for this session."
        nextTab="splat"
        nextLabel="View result"
      />
      <div className="flex-1 overflow-y-auto p-6" style={{ color: 'var(--text)' }}>
      <div className="mx-auto flex flex-col gap-6" style={{ maxWidth: 720 }}>

        {/* ---- Start card ---- */}
        <section
          className="p-5 flex flex-col gap-4"
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

          {preflightLoading && (
            <p className="text-xs" style={{ color: 'var(--text-muted)', margin: 0 }}>
              Checking dataset quality…
            </p>
          )}

          {preflightReport && (
            <div
              className="flex flex-col gap-3"
              style={{
                padding: 12,
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <h3 className="text-sm font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
                    Preflight quality
                  </h3>
                  <p className="text-xs" style={{ color: 'var(--text-muted)', margin: '4px 0 0' }}>
                    {preflightReport.usable_frames}/{preflightReport.total_frames} usable frames · {preflightReport.recommended_action}
                  </p>
                </div>
                <span
                  className="text-xs rounded"
                  style={{
                    alignSelf: 'flex-start',
                    padding: '2px 8px',
                    background: preflightReport.safe_to_reconstruct === 'yes'
                      ? 'var(--success-soft)'
                      : preflightReport.safe_to_reconstruct === 'caution'
                      ? 'var(--warning-soft)'
                      : 'var(--danger-soft)',
                    color: preflightReport.safe_to_reconstruct === 'yes'
                      ? 'var(--success)'
                      : preflightReport.safe_to_reconstruct === 'caution'
                      ? 'var(--warning)'
                      : 'var(--danger)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {preflightReport.score}/100 · {preflightReport.safe_to_reconstruct.toUpperCase()}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
                <span>GPS: {preflightReport.gps.completeness_pct}% complete</span>
                <span>Timestamps: {preflightReport.timestamps.completeness_pct}% complete</span>
                <span>Blur: {preflightReport.quality.blur_pct}%</span>
                <span>Exposure: {(preflightReport.quality.dark_pct + preflightReport.quality.bright_pct).toFixed(1)}%</span>
                <span>Gaps: {preflightReport.timestamps.gap_count}</span>
                <span>Duplicates: {preflightReport.timestamps.duplicate_frames}</span>
                <span>Footprints: {preflightReport.coverage.footprint_coverage_pct}%</span>
                <span>
                  Overlap: {preflightReport.coverage.estimated_overlap_pct === null
                    ? 'n/a'
                    : `${preflightReport.coverage.estimated_overlap_pct}%`}
                </span>
              </div>

              {preflightReport.warnings.length > 0 && (
                <ul className="text-xs" style={{ color: 'var(--warning)', margin: 0, paddingLeft: 18 }}>
                  {preflightReport.warnings.slice(0, 4).map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                  {preflightReport.warnings.length > 4 && (
                    <li>{preflightReport.warnings.length - 4} more warnings</li>
                  )}
                </ul>
              )}
            </div>
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
                  {p === 'quick' ? 'Quick: fewer iterations, faster' : 'Full: best quality, slower'}
                </span>
              </label>
            ))}
          </div>

          {/* Target area */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Target area (optional, crops images to polygon before COLMAP)
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
              <option value="">No crop: use all usable frames</option>
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
            className="p-5 flex flex-col gap-3"
            style={{ background: 'var(--surface)', border: '1px solid var(--accent)' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h2 className="text-base font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
                Reconstruction #{activeJob.id}: In Progress
              </h2>
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={() => cancelMutation.mutate(activeJob.id)}
                disabled={cancelMutation.isPending}
                style={{
                  borderRadius: 4, padding: '3px 10px', fontSize: 12,
                }}
              >
                {cancelMutation.isPending ? 'Cancelling…' : 'Cancel'}
              </Button>
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
            className="p-5 flex flex-col gap-3"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
          >
            <h2 className="text-base font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
              History
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0, borderTop: '1px solid var(--border)' }}>
              {sessionJobs.map((job, idx) => (
                <div key={job.id}>
                  <div
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '10px 2px',
                      borderBottom: idx < sessionJobs.length - 1 ? '1px solid var(--border)' : 'none',
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
                        href={`${API_BASE_URL}/reconstruction/${job.id}/splat?lod=full`}
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
                  {job.status === 'complete' && (
                    <div style={{ padding: '0 2px 8px' }}>
                      <QualityReportInline jobId={job.id} />
                    </div>
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
    </div>
  )
}