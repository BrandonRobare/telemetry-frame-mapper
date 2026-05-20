import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from '../../shared/api/client'
import { Button } from '../../shared/components/Button'
import { useToast } from '../../shared/hooks/useToast'
import { useMapStore } from '../../shared/stores/mapStore'
import type { ComparisonCell, ComparisonDiff, Job, Session, SessionComparison } from '../../types/api'
import { formatComparisonSummary, normalizeCellsForOverlay, visibleComparisonCells } from './formatDiff'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

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

function DiffOverlay({ cells }: { cells: ComparisonCell[] }) {
  const normalized = normalizeCellsForOverlay(cells)
  return (
    <div
      style={{
        height: 360,
        borderRadius: 6,
        border: '1px solid var(--border)',
        background: '#05070a',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ width: '100%', height: '100%' }}>
        <rect x="0" y="0" width="100" height="100" fill="#05070a" />
        {normalized.map((cell, index) => (
          <circle
            key={`${cell.type}-${index}-${cell.x}-${cell.y}-${cell.z}`}
            cx={cell.overlayX}
            cy={cell.overlayY}
            r={cell.type === 'new' ? 1.8 : 1.5}
            fill={cell.type === 'new' ? '#22c55e' : '#ef4444'}
            opacity="0.78"
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
  const { selectedSessionId } = useMapStore()
  const { addToast } = useToast()
  const qc = useQueryClient()
  const { data: sessions = [] } = useSessions()
  const { data: jobs = [], isLoading } = useJobs()
  const [reconstructionAId, setReconstructionAId] = useState<number | null>(null)
  const [reconstructionBId, setReconstructionBId] = useState<number | null>(null)
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
  const { data: comparison } = useComparison(comparisonId)
  const { data: diff } = useComparisonDiff(comparisonId, comparison?.status === 'complete')

  useEffect(() => {
    if (reconstructionAId !== null || completedJobs.length === 0) return
    const preferred = completedJobs.find((job) => job.session_id === selectedSessionId)
    setReconstructionAId((preferred ?? completedJobs[0]).id)
  }, [completedJobs, reconstructionAId, selectedSessionId])

  useEffect(() => {
    if (reconstructionBId !== null || completedJobs.length < 2) return
    const firstDifferent = completedJobs.find((job) => job.id !== reconstructionAId)
    if (firstDifferent) setReconstructionBId(firstDifferent.id)
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

  return (
    <div className="flex-1 overflow-y-auto p-6" style={{ color: 'var(--text)' }}>
      <div className="mx-auto flex flex-col gap-6" style={{ maxWidth: 980 }}>
        <section
          className="rounded-lg p-5 flex flex-col gap-4"
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
          )}
        </section>

        <section
          className="rounded-lg p-5 flex flex-col gap-4"
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
                <input type="checkbox" checked={showNew} onChange={(event) => setShowNew(event.target.checked)} />
                New
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={showRemoved}
                  onChange={(event) => setShowRemoved(event.target.checked)}
                />
                Removed
              </label>
              {comparison?.status === 'complete' && (
                <a
                  href={`${BASE_URL}/comparisons/${comparison.id}/diff.geojson`}
                  download={`comparison_${comparison.id}.geojson`}
                  style={{ color: '#58a6ff', textDecoration: 'none' }}
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
  )
}

const selectStyle = {
  background: 'var(--bg)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text)',
  padding: '6px 8px',
  fontSize: 13,
  fontFamily: 'inherit',
}
