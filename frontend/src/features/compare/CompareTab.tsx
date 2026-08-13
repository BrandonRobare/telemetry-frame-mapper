import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiUrl, get, post } from '../../shared/api/client'
import { Button } from '../../shared/components/Button'
import { useToast } from '../../shared/hooks/useToast'
import { useMapStore } from '../../shared/stores/mapStore'
import type {
  ComparisonCell,
  ComparisonDiff,
  Job,
  Session,
  SessionComparison,
  SiteTrend,
} from '../../types/api'
import { formatComparisonSummary, normalizeCellsForOverlay, visibleComparisonCells } from './formatDiff'
import { formatTrendDate, formatTrendPercent, formatTrendValue } from './formatTrends'
import { comparisonGridJobs } from './comparisonGrid'
import CompareMapPane from './CompareMapPane'
import TabHeader from '../../shared/components/TabHeader'


function useSessions() {
  return useQuery<Session[]>({
    queryKey: ['sessions'],
    queryFn: () => get<Session[]>('/sessions/'),
  })
}

function useJobs() {
  return useQuery<Job[]>({
    queryKey: ['jobs', 'compare'],
    queryFn: () => get<Job[]>('/jobs/'),
  })
}

function useComparison(comparisonId: number | null) {
  return useQuery<SessionComparison>({
    queryKey: ['comparison', comparisonId],
    queryFn: () => get<SessionComparison>(`/comparisons/${comparisonId!}`),
    enabled: comparisonId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'running' ? 2000 : false
    },
  })
}

function useComparisonDiff(comparisonId: number | null, ready: boolean) {
  return useQuery<ComparisonDiff>({
    queryKey: ['comparison-diff', comparisonId],
    queryFn: () => get<ComparisonDiff>(`/comparisons/${comparisonId!}/diff`),
    enabled: comparisonId !== null && ready,
  })
}

function useProjectTrends(projectId: number | null) {
  return useQuery<SiteTrend>({
    queryKey: ['project-trends', projectId],
    queryFn: () => get<SiteTrend>(`/projects/${projectId!}/trends`),
    enabled: projectId !== null,
    staleTime: 30_000,
  })
}

function DiffOverlay({ cells }: { cells: ComparisonCell[] }) {
  const normalized = normalizeCellsForOverlay(cells)
  // Diff dots use literal hex (SVG fill attribute won't resolve CSS vars), kept in
  // sync with the warm tokens: --success (sage, new) and --danger-accent (brick, removed).
  return (
    <div
      style={{
        height: 360,
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--border)',
        background: 'var(--surface-2)',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ width: '100%', height: '100%' }}>
        <rect x="0" y="0" width="100" height="100" fill="#F1E8D2" />
        {normalized.map((cell, index) => (
          <circle
            key={`${cell.type}-${index}-${cell.x}-${cell.y}-${cell.z}`}
            cx={cell.overlayX}
            cy={cell.overlayY}
            r={cell.type === 'new' ? 1.8 : 1.5}
            fill={cell.type === 'new' ? '#4F6349' : '#B5503C'}
            opacity="0.82"
          />
        ))}
      </svg>
      {normalized.length === 0 && (
        <div
          className="flex items-center justify-center"
          style={{ position: 'absolute', inset: 0, color: 'var(--text-muted)', fontSize: 13 }}
        >
          No diff cells for the selected layers
        </div>
      )}
    </div>
  )
}

function optionLabel(job: Job, sessionsById: Map<number, string>) {
  return `${sessionsById.get(job.session_id) ?? `Session ${job.session_id}`} · Reconstruction #${job.id}`
}

export default function CompareTab() {
  const { selectedProjectId, selectedSessionId, setSession, setTargetReconstructionId, setRequestedTab } = useMapStore()
  const { addToast } = useToast()
  const qc = useQueryClient()
  const { data: sessions = [] } = useSessions()
  const { data: jobs = [], isLoading } = useJobs()
  const [reconstructionAId, setReconstructionAId] = useState<number | null>(null)
  const [reconstructionBId, setReconstructionBId] = useState<number | null>(null)
  const [reconstructionCId, setReconstructionCId] = useState<number | null>(null)
  const [reconstructionDId, setReconstructionDId] = useState<number | null>(null)
  const [comparisonId, setComparisonId] = useState<number | null>(null)
  const [showNew, setShowNew] = useState(true)
  const [showRemoved, setShowRemoved] = useState(true)

  const sessionsById = useMemo(
    () => new Map(sessions.map((session) => [session.id, session.name])),
    [sessions],
  )
  const completedJobs = useMemo(
    () => jobs.filter((job) => job.status === 'complete'),
    [jobs],
  )
  const recA = completedJobs.find((job) => job.id === reconstructionAId) ?? null
  const recB = completedJobs.find((job) => job.id === reconstructionBId) ?? null
  const gridJobs = comparisonGridJobs(completedJobs, [reconstructionAId, reconstructionBId, reconstructionCId, reconstructionDId])
  const { data: comparison } = useComparison(comparisonId)
  const { data: diff } = useComparisonDiff(comparisonId, comparison?.status === 'complete')
  const { data: trends, isLoading: trendsLoading } = useProjectTrends(selectedProjectId)

  useEffect(() => {
    if (reconstructionAId !== null || completedJobs.length === 0) return
    const preferred = completedJobs.find((job) => job.session_id === selectedSessionId)

    queueMicrotask(() => setReconstructionAId((preferred ?? completedJobs[0]).id))
  }, [completedJobs, reconstructionAId, selectedSessionId])

  useEffect(() => {
    if (reconstructionBId !== null || completedJobs.length < 2) return
    const firstDifferent = completedJobs.find((job) => job.id !== reconstructionAId)

    if (firstDifferent) queueMicrotask(() => setReconstructionBId(firstDifferent.id))
  }, [completedJobs, reconstructionAId, reconstructionBId])

  const compareMutation = useMutation({
    mutationFn: () => {
      if (!recA || !recB) throw new Error('Select two completed reconstructions')
      return post<SessionComparison>('/comparisons', {
        session_a_id: recA.session_id,
        session_b_id: recB.session_id,
        reconstruction_a_id: recA.id,
        reconstruction_b_id: recB.id,
      })
    },
    onSuccess: (created) => {
      setComparisonId(created.id)
      addToast('Comparison started', 'success')
      qc.invalidateQueries({ queryKey: ['comparison', created.id] })
    },
    onError: (err: Error) => addToast(err.message, 'error'),
  })

  const visibleCells = visibleComparisonCells(diff, showNew, showRemoved)
  const canCompare = !!recA && !!recB && recA.id !== recB.id

  function openInViewer(job: Job) {
    setSession(job.session_id)
    setTargetReconstructionId(job.id)
    setRequestedTab('splat')
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <TabHeader
        title="Compare"
        description="Diff two completed reconstructions to see what changed."
      />
      <div className="flex-1 overflow-y-auto p-6" style={{ color: 'var(--text)' }}>
      <div className="mx-auto flex flex-col gap-6" style={{ maxWidth: 980 }}>
        <section
          className="p-5 flex flex-col gap-3"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <div>
            <h2 className="text-base font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
              Site trend
            </h2>
            <p className="text-sm" style={{ color: 'var(--text-muted)', margin: '4px 0 0' }}>
              Existing session, coverage, and completed-reconstruction metrics for this project.
            </p>
          </div>
          {selectedProjectId === null && (
            <p className="text-sm" style={{ color: 'var(--text-muted)', margin: 0 }}>
              Select a project to see its flight trend.
            </p>
          )}
          {selectedProjectId !== null && trendsLoading && (
            <p className="text-sm" style={{ color: 'var(--text-muted)', margin: 0 }}>
              Loading site trend…
            </p>
          )}
          {trends && trends.points.length === 0 && (
            <p className="text-sm" style={{ color: 'var(--text-muted)', margin: 0 }}>
              No sessions have been imported for this project.
            </p>
          )}
          {trends && trends.points.length > 0 && (
            <div style={{ overflowX: 'auto' }}>
              <table className="w-full text-sm" style={{ borderCollapse: 'collapse', minWidth: 720 }}>
                <caption className="sr-only">Time-ordered metrics for the selected project</caption>
                <thead style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                  <tr>
                    {['Flight', 'Session', 'Usable', 'Coverage', 'Registered', 'PSNR', 'SSIM'].map((label) => (
                      <th key={label} scope="col" className="text-left" style={trendCellStyle}>{label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {trends.points.map((point) => (
                    <tr key={point.session_id} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={trendCellStyle}>{formatTrendDate(point.imported_at)}</td>
                      <th scope="row" className="text-left font-medium" style={trendCellStyle}>{point.session_name}</th>
                      <td style={trendCellStyle}>{formatTrendPercent(point.usable_pct)}</td>
                      <td style={trendCellStyle}>{formatTrendPercent(point.coverage_pct)}</td>
                      <td style={trendCellStyle}>{point.frames_registered ?? '—'}</td>
                      <td style={trendCellStyle}>{formatTrendValue(point.psnr)}</td>
                      <td style={trendCellStyle}>{formatTrendValue(point.ssim, 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs" style={{ color: 'var(--text-muted)', margin: 0 }}>
            — means that metric has not been recorded yet. No trend calculation is run in the background.
          </p>
        </section>

        <section
          className="p-5 flex flex-col gap-4"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <h2 className="text-base font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
            Multi-Session Comparison
          </h2>

          {isLoading && (
            <p className="text-sm" style={{ color: 'var(--text-muted)', margin: 0 }}>
              Loading reconstructions…
            </p>
          )}

          {!isLoading && completedJobs.length < 2 && (
            <p className="text-sm" style={{ color: 'var(--text-muted)', margin: 0 }}>
              At least two completed reconstructions are required.
            </p>
          )}

          {completedJobs.length >= 2 && (
            <>
            <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 1fr auto' }}>
              <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                Baseline
                <select
                  value={reconstructionAId ?? ''}
                  onChange={(event) => setReconstructionAId(Number(event.target.value))}
                  style={selectStyle}
                >
                  {completedJobs.map((job) => (
                    <option key={job.id} value={job.id}>{optionLabel(job, sessionsById)}</option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                Updated
                <select
                  value={reconstructionBId ?? ''}
                  onChange={(event) => setReconstructionBId(Number(event.target.value))}
                  style={selectStyle}
                >
                  {completedJobs.map((job) => (
                    <option key={job.id} value={job.id}>{optionLabel(job, sessionsById)}</option>
                  ))}
                </select>
              </label>

              <Button
                variant="primary"
                disabled={!canCompare || compareMutation.isPending}
                onClick={() => compareMutation.mutate()}
                style={{ alignSelf: 'end' }}
              >
                {compareMutation.isPending ? 'Starting…' : 'Compare'}
              </Button>
            </div>
            <div>
              <p className="text-xs" style={{ color: 'var(--text-muted)', margin: '0 0 8px' }}>
                Add up to two completed reconstructions for a 3–4-up synchronized map-context review. The first two remain the backend diff pair.
              </p>
              <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 1fr' }}>
                <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                  Third view (optional)
                  <select value={reconstructionCId ?? ''} onChange={(event) => setReconstructionCId(event.target.value ? Number(event.target.value) : null)} style={selectStyle}>
                    <option value="">None</option>
                    {completedJobs.map((job) => <option key={job.id} value={job.id}>{optionLabel(job, sessionsById)}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                  Fourth view (optional)
                  <select value={reconstructionDId ?? ''} onChange={(event) => setReconstructionDId(event.target.value ? Number(event.target.value) : null)} style={selectStyle}>
                    <option value="">None</option>
                    {completedJobs.map((job) => <option key={job.id} value={job.id}>{optionLabel(job, sessionsById)}</option>)}
                  </select>
                </label>
              </div>
            </div>
            {gridJobs.length >= 2 && (
              <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${gridJobs.length}, minmax(0, 1fr))` }}>
                {gridJobs.map((job) => (
                  <article key={job.id} className="p-3 flex flex-col gap-2" style={{ border: '1px solid var(--border)', background: 'var(--surface-2)' }}>
                    <div>
                      <p className="text-xs font-medium" style={{ color: 'var(--text)', margin: 0 }}>{sessionsById.get(job.session_id) ?? `Session ${job.session_id}`}</p>
                      <p className="text-xs" style={{ color: 'var(--text-muted)', margin: '2px 0 0' }}>Reconstruction #{job.id} · {job.preset}</p>
                    </div>
                    <p className="text-xs" style={{ color: 'var(--text-muted)', margin: 0 }}>{job.frames_used} frames · {job.status}</p>
                    <CompareMapPane reconstructionId={job.id} sessionId={job.session_id} />
                    <Button variant="ghost" size="sm" onClick={() => openInViewer(job)}>Open synced 3D view</Button>
                  </article>
                ))}
              </div>
            )}
            </>
          )}
        </section>

        <section
          className="p-5 flex flex-col gap-4"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
                Diff Overlay
              </h2>
              <p className="text-sm" style={{ color: 'var(--text-muted)', margin: '4px 0 0' }}>
                {formatComparisonSummary(diff)}
              </p>
            </div>
            <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--text-muted)' }}>
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={showNew}
                  onChange={(event) => setShowNew(event.target.checked)}
                  style={{ accentColor: 'var(--accent)' }}
                />
                New
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={showRemoved}
                  onChange={(event) => setShowRemoved(event.target.checked)}
                  style={{ accentColor: 'var(--accent)' }}
                />
                Removed
              </label>
              {comparison?.status === 'complete' && (
                <a
                  href={apiUrl(`/comparisons/${comparison.id}/diff.geojson`)}
                  download={`comparison_${comparison.id}.geojson`}
                  style={{ color: 'var(--accent-strong)', textDecoration: 'none' }}
                >
                  Export GeoJSON
                </a>
              )}
            </div>
          </div>

          {comparison && comparison.status !== 'complete' && (
            <p className="text-sm" style={{ color: 'var(--text-muted)', margin: 0 }}>
              Comparison #{comparison.id}: {comparison.status}
              {comparison.error_msg ? ` · ${comparison.error_msg}` : ''}
            </p>
          )}

          <DiffOverlay cells={visibleCells} />
        </section>
      </div>
    </div>
    </div>
  )
}

const selectStyle = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--text)',
  padding: '6px 8px',
  fontSize: 13,
  fontFamily: 'inherit',
}

const trendCellStyle = { padding: '8px 10px 8px 0', whiteSpace: 'nowrap' as const }
