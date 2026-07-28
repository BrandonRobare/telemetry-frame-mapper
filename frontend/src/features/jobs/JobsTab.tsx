import { useState, type ComponentProps } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../../shared/api/client'
import {
  isLiveReconstructionStatus,
  useReconstructionStatusEvents,
} from '../../shared/api/reconstructionStatusEvents'
import { formatEta } from '../../shared/time'
import type { Job, SystemResources, SystemTool, WorkflowStatus } from '../../types/api'
import { SkeletonRow } from '../../shared/components/Skeleton'
import TabHeader from '../../shared/components/TabHeader'
import { Button } from '../../shared/components/Button'
import { Badge } from '../../shared/components/Badge'
import { useToast } from '../../shared/hooks/useToast'
import { filterReconstructionLogLines } from './logPanel'

const HISTORY_PAGE_SIZE = 10
type JobStatusFilter = 'all' | Job['status']

function jobsPath(skip: number, limit: number, status: JobStatusFilter) {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) })
  if (status !== 'all') params.set('status', status)
  return `/jobs/?${params.toString()}`
}

function useJobs(
  skip = 0,
  limit = 50,
  status: JobStatusFilter = 'all',
  sseConnectedIds: ReadonlySet<number> = new Set()
) {
  return useQuery<Job[]>({
    queryKey: ['jobs', skip, limit, status],
    queryFn: () => get<Job[]>(jobsPath(skip, limit, status)),
    refetchInterval: (query) => {
      const jobs = query.state.data ?? []
      const needsPollingFallback = jobs.some((j) =>
        isLiveReconstructionStatus(j.status) && !sseConnectedIds.has(j.id)
      )
      return needsPollingFallback ? 3000 : 30_000
    },
  })
}

function useSystemResources() {
  return useQuery<SystemResources>({
    queryKey: ['system-resources'],
    queryFn: () => get<SystemResources>('/system/resources'),
    refetchInterval: 3000,
  })
}

function ResourceBar() {
  const { data: res } = useSystemResources()
  if (!res) return <div style={{ height: 33, borderBottom: '1px solid var(--border)', flexShrink: 0 }} />
  const ramPct = ((res.ram_used_gb / res.ram_total_gb) * 100).toFixed(0)
  const diskPct = ((res.disk_used_gb / res.disk_total_gb) * 100).toFixed(0)
  return (
    <>
      <div
        style={{
          display: 'flex', gap: 20, padding: '7px 16px',
          background: 'var(--surface)', borderBottom: '1px solid var(--border)',
          fontSize: 11, color: 'var(--text-muted)', alignItems: 'center', flexShrink: 0,
        }}
      >
        <span>CPU <strong style={{ color: 'var(--text)' }}>{res.cpu_pct.toFixed(0)}%</strong></span>
        <span>
          RAM{' '}
          <strong style={{ color: 'var(--text)' }}>{res.ram_used_gb.toFixed(1)}</strong>
          {' / '}{res.ram_total_gb.toFixed(0)} GB ({ramPct}%)
        </span>
        {res.gpu_pct != null && (
          <span>GPU <strong style={{ color: 'var(--success)' }}>{res.gpu_pct.toFixed(0)}%</strong></span>
        )}
        {res.vram_used_gb != null && res.vram_total_gb != null && (
          <span>
            VRAM{' '}
            <strong style={{ color: 'var(--success)' }}>{res.vram_used_gb.toFixed(1)}</strong>
            {' / '}{res.vram_total_gb.toFixed(0)} GB
          </span>
        )}
        {res.gpu_name && <span title={res.gpu_name}>GPU {res.gpu_name}</span>}
        <span style={{ marginLeft: 'auto' }}>Disk {diskPct}% used</span>
      </div>
      <SystemHealthDashboard resources={res} />
    </>
  )
}

function formatInstallCommands(tool: SystemTool) {
  return Object.entries(tool.install_commands)
    .map(([platform, command]) => `${platform}: ${command}`)
    .join('\n')
}

function ToolStatusCard({ tool }: { tool: SystemTool }) {
  const { addToast } = useToast()
  const installText = formatInstallCommands(tool)
  async function copyInstallCommands() {
    try {
      await navigator.clipboard.writeText(installText)
      addToast(`${tool.label} install commands copied`, 'success')
    } catch {
      addToast(`Failed to copy ${tool.label} install commands`, 'error')
    }
  }

  return (
    <div
      style={{
        minWidth: 0, padding: 10, borderRadius: 'var(--radius-md)',
        border: '1px solid var(--border)', background: 'var(--surface)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span className="text-xs font-semibold" style={{ color: 'var(--text)' }}>{tool.label}</span>
        <Badge color={tool.available ? 'sage' : 'red'} className="rounded" style={{ padding: '1px 6px', marginLeft: 'auto' }}>
          {tool.available ? 'Available' : 'Unavailable'}
        </Badge>
      </div>
      <div style={{ color: 'var(--text-muted)', fontSize: 11, lineHeight: 1.5 }}>
        <div title={tool.path ?? undefined} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          Path: {tool.path ?? 'Not found'}
        </div>
        <div title={tool.version ?? undefined} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          Version: {tool.version ?? 'Unknown'}
        </div>
        {tool.cuda_available != null && <div>CUDA: {tool.cuda_available ? 'Yes' : 'No'}</div>}
        {tool.error && <div style={{ color: 'var(--danger)' }}>Error: {tool.error}</div>}
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={copyInstallCommands}
        style={{
          marginTop: 8,
          padding: '4px 8px',
        }}
      >
        Copy install
      </Button>
    </div>
  )
}

function WorkflowStatusPill({ workflow }: { workflow: WorkflowStatus }) {
  return (
    <div
      title={workflow.missing.length > 0 ? `Missing: ${workflow.missing.join(', ')}` : undefined}
      style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '6px 8px',
        borderRadius: 'var(--radius-sm)', background: workflow.available ? 'var(--success-soft)' : 'var(--surface)',
        border: '1px solid var(--border)', color: workflow.available ? 'var(--success)' : 'var(--text-muted)',
        fontSize: 11,
      }}
    >
      <span>{workflow.available ? '●' : '○'}</span>
      <span>{workflow.label}</span>
      {!workflow.available && workflow.missing.length > 0 && <span>({workflow.missing.length} missing)</span>}
    </div>
  )
}

function SystemHealthDashboard({ resources }: { resources: SystemResources }) {
  return (
    <section
      style={{
        padding: '12px 16px', borderBottom: '1px solid var(--border)', background: 'var(--surface-2)',
        flexShrink: 0,
      }}
      aria-label="System health dashboard"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
        <h2 className="text-sm font-semibold" style={{ color: 'var(--text)', margin: 0, marginRight: 'auto' }}>
          System Health
        </h2>
        <span className="text-xs" style={{ color: resources.gpu_available ? 'var(--success)' : 'var(--text-muted)' }}>
          {resources.gpu_available
            ? `${resources.gpu_name ?? 'NVIDIA GPU'} · ${resources.vram_total_gb ?? '?'} GB VRAM`
            : 'No NVIDIA GPU detected'}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        {resources.workflows.map((workflow) => (
          <WorkflowStatusPill key={workflow.key} workflow={workflow} />
        ))}
      </div>
      <div
        style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 8,
        }}
      >
        {resources.tools.map((tool) => <ToolStatusCard key={tool.key} tool={tool} />)}
      </div>
    </section>
  )
}

function useReconstructionLog(id: number, enabled: boolean, limit = 100) {
  return useQuery<{ lines: string[] }>({
    queryKey: ['rec-log', id, limit],
    queryFn: () => get(`/reconstruction/${id}/log?limit=${limit}`),
    enabled,
    refetchInterval: enabled ? 2000 : false,
  })
}

function LogPanel({ recId, isActive }: { recId: number; isActive: boolean }) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const { addToast } = useToast()
  const { data } = useReconstructionLog(recId, open && isActive)
  const lines = data?.lines ?? []
  const filteredLines = filterReconstructionLogLines(lines, filter)
  const hasFilter = filter.trim().length > 0

  async function copyLog() {
    try {
      await navigator.clipboard.writeText(filteredLines.join('\n'))
      addToast(hasFilter ? 'Filtered log copied' : 'Log copied', 'success')
    } catch {
      addToast('Failed to copy log', 'error')
    }
  }

  return (
    <div style={{ marginTop: 6 }}>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => setOpen((o) => !o)}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          fontSize: 11, color: 'var(--text-muted)', fontFamily: 'inherit',
          padding: 0,
        }}
      >
        {open ? '▾' : '▸'} {open ? 'Hide' : 'Show'} log ({lines.length} lines)
      </Button>
      {open && (
        <div style={{ marginTop: 4 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 4, alignItems: 'center' }}>
            <input
              aria-label="Filter reconstruction log"
              placeholder="Filter log..."
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              style={{
                flex: 1,
                minWidth: 0,
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--surface)',
                color: 'var(--text)',
                fontFamily: 'inherit',
                fontSize: 11,
                padding: '4px 6px',
              }}
            />
            <Button size="sm" variant="ghost" onClick={copyLog} disabled={filteredLines.length === 0}>
              Copy {hasFilter ? 'filtered' : 'log'}
            </Button>
          </div>
          <div
            style={{
              padding: '6px 8px', borderRadius: 'var(--radius-sm)',
              background: 'var(--surface-2)', maxHeight: 180, overflowY: 'auto',
              fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text)',
              border: '1px solid var(--border)',
            }}
          >
            {lines.length === 0 ? (
              <span style={{ color: 'var(--text-muted)' }}>No log entries yet.</span>
            ) : filteredLines.length === 0 ? (
              <span style={{ color: 'var(--text-muted)' }}>No log entries match “{filter}”.</span>
            ) : (
              filteredLines.map((line, i) => <div key={`${i}-${line.slice(0, 8)}`}>{line}</div>)
            )}
          </div>
        </div>
      )}
    </div>
  )
}

const STATUS_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  pending:        { bg: 'var(--tan-soft)',     text: 'var(--tan-text)',      label: 'Pending' },
  running_colmap: { bg: 'var(--warning-soft)', text: 'var(--warning)',       label: 'COLMAP' },
  running_gsplat: { bg: 'var(--accent-soft)',  text: 'var(--accent-strong)', label: 'Gaussian' },
  complete:       { bg: 'var(--success-soft)', text: 'var(--success)',       label: 'Complete' },
  failed:         { bg: 'var(--danger-soft)',  text: 'var(--danger)',        label: 'Failed' },
}

function jobStatusBadgeColor(status: string): ComponentProps<typeof Badge>['color'] {
  if (status === 'complete') return 'sage'
  if (status === 'failed') return 'red'
  if (status === 'pending') return 'tan'
  if (status === 'running_colmap') return 'amber'
  if (status === 'running_gsplat') return 'terracotta'
  return 'muted'
}

function formatDuration(start: string, end: string | null): string {
  const startMs = new Date(start).getTime()
  const endMs = end ? new Date(end).getTime() : Date.now()
  const sec = Math.round((endMs - startMs) / 1000)
  if (sec < 60) return `${sec}s`
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
}

export default function JobsTab() {
  const [historyPage, setHistoryPage] = useState(0)
  const [statusFilter, setStatusFilter] = useState<JobStatusFilter>('all')
  const [search, setSearch] = useState('')
  const [sseConnectedIds, setSseConnectedIds] = useState<ReadonlySet<number>>(new Set())
  const { data: activeJobs, isLoading: isLoadingActive } = useJobs(0, 50, 'all', sseConnectedIds)
  const { data: historyJobs, isLoading: isLoadingHistory } = useJobs(
    historyPage * HISTORY_PAGE_SIZE,
    HISTORY_PAGE_SIZE + 1,
    statusFilter,
    sseConnectedIds
  )
  useReconstructionStatusEvents(activeJobs, setSseConnectedIds)
  const isLoading = isLoadingActive && isLoadingHistory

  if (isLoading) {
    return (
      <div className="flex flex-col flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto p-6">
          <div className="mx-auto" style={{ maxWidth: 800, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonRow key={i} />
            ))}
          </div>
        </div>
      </div>
    )
  }

  const activeList = activeJobs ?? []
  const historyPageJobs = historyJobs ?? []
  const hasNextHistoryPage = historyPageJobs.length > HISTORY_PAGE_SIZE
  const searchNeedle = search.trim().toLowerCase()

  // Rendered inside the layout rather than returned early: System Health lives in
  // <ResourceBar />, and it is the only place showing whether ffmpeg/exiftool/
  // COLMAP/torch/gsplat were found, plus the install commands. Returning early
  // here hid the first-run diagnostic screen until after a job had succeeded —
  // exactly when it is no longer needed.
  const noJobsAtAll =
    activeList.length === 0 && historyPageJobs.length === 0 && !searchNeedle && statusFilter === 'all'

  const running = activeList.filter((j) => isLiveReconstructionStatus(j.status))
  const done = historyPageJobs
    .filter((j) => !isLiveReconstructionStatus(j.status))
    .slice(0, HISTORY_PAGE_SIZE)
    .filter((job) => {
      if (!searchNeedle) return true
      return [
        String(job.id),
        job.status,
        String(job.session_id),
        job.preset,
        job.step,
        job.error_msg ?? '',
      ].some((value) => value.toLowerCase().includes(searchNeedle))
    })

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <TabHeader
        title="Jobs"
        description="Every reconstruction job across all sessions, with live system resources."
      />
      <ResourceBar />
      <div className="flex-1 overflow-y-auto p-6" style={{ color: 'var(--text)' }}>
        <div className="mx-auto" style={{ maxWidth: 800 }}>

        {noJobsAtAll && (
          <div
            className="flex items-center justify-center"
            style={{ color: 'var(--text-muted)', padding: '48px 0' }}
          >
            No jobs yet. Start a reconstruction from the Reconstruct tab.
          </div>
        )}

        {running.length > 0 && (
          <section style={{ marginBottom: 24 }}>
            <h2 className="text-sm font-semibold" style={{ color: 'var(--text)', marginBottom: 12 }}>
              Active ({running.length})
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {running.map((job) => {
                const s = STATUS_BADGE[job.status]
                const eta = formatEta(job.started_at, job.progress_pct)
                return (
                  <div
                    key={job.id}
                    style={{
                      background: 'var(--surface)',
                      border: '1px solid var(--accent)',
                      borderRadius: 'var(--radius-md)', padding: '14px 16px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>#{job.id}</span>
                      <Badge color={jobStatusBadgeColor(job.status)} className="rounded" style={{ padding: '2px 8px' }}>
                        {s.label}
                      </Badge>
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                        Session {job.session_id} · {job.preset} · {job.frames_used} frames
                      </span>
                      {job.started_at && (
                        <span className="text-xs" style={{ color: 'var(--text-muted)', marginLeft: 'auto' }}>
                          {formatDuration(job.started_at, null)}
                        </span>
                      )}
                    </div>
                    <div style={{ height: 4, borderRadius: 2, background: 'var(--surface-2)', overflow: 'hidden' }}>
                      <div
                        style={{
                          height: '100%', borderRadius: 2,
                          background: 'var(--accent)',
                          width: `${job.progress_pct}%`,
                          transition: 'width 0.5s ease',
                        }}
                      />
                    </div>
                    <p className="text-xs" style={{ color: 'var(--text-muted)', marginTop: 6, marginBottom: 0 }}>
                      {job.progress_pct.toFixed(1)}% · {job.step || 'Initializing…'}
                      {eta && ` · ${eta}`}
                    </p>
                    <LogPanel recId={job.id} isActive={true} />
                  </div>
                )
              })}
            </div>
          </section>
        )}

        <section style={noJobsAtAll ? { display: 'none' } : undefined}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
            <h2 className="text-sm font-semibold" style={{ color: 'var(--text)', margin: 0, marginRight: 'auto' }}>
              History
            </h2>
            <input
              aria-label="Search job history"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search jobs…"
              style={{
                minWidth: 180, padding: '6px 8px', borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)',
                fontSize: 12,
              }}
            />
            <select
              aria-label="Filter job history by status"
              value={statusFilter}
              onChange={(event) => {
                setStatusFilter(event.target.value as JobStatusFilter)
                setHistoryPage(0)
              }}
              style={{
                padding: '6px 8px', borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)',
                fontSize: 12,
              }}
            >
              <option value="all">All statuses</option>
              <option value="complete">Complete</option>
              <option value="failed">Failed</option>
              <option value="pending">Pending</option>
              <option value="running_colmap">COLMAP</option>
              <option value="running_gsplat">Gaussian</option>
            </select>
          </div>
          {done.length === 0 ? (
            <div style={{ padding: '16px 10px', color: 'var(--text-muted)', fontSize: 13 }}>
              No history jobs match the current search and status filter.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['#', 'Status', 'Session', 'Preset', 'Frames', 'Duration', 'Step / Error'].map((h) => (
                    <th
                      key={h}
                      className="text-left text-xs font-medium"
                      style={{ padding: '6px 10px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {done.map((job) => {
                  const s = STATUS_BADGE[job.status] ?? { bg: 'var(--surface)', text: 'var(--text)', label: job.status }
                  return (
                    <tr key={job.id} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td style={{ padding: '8px 10px', color: 'var(--text-muted)' }}>{job.id}</td>
                      <td style={{ padding: '8px 10px' }}>
                        <Badge color={jobStatusBadgeColor(job.status)} className="rounded" style={{ padding: '2px 7px' }}>
                          {s.label}
                        </Badge>
                      </td>
                      <td style={{ padding: '8px 10px', color: 'var(--text-muted)' }}>{job.session_id}</td>
                      <td style={{ padding: '8px 10px', color: 'var(--text-muted)' }}>{job.preset}</td>
                      <td style={{ padding: '8px 10px', color: 'var(--text-muted)' }}>{job.frames_used}</td>
                      <td style={{ padding: '8px 10px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                        {job.started_at ? formatDuration(job.started_at, job.completed_at) : '—'}
                      </td>
                      <td
                        style={{
                          padding: '8px 10px',
                          color: job.status === 'failed' ? 'var(--danger, #f85149)' : 'var(--text-muted)',
                          maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}
                      >
                        {job.error_msg ?? job.step ?? '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, color: 'var(--text-muted)', fontSize: 12 }}>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={historyPage === 0}
              onClick={() => setHistoryPage((page) => Math.max(0, page - 1))}
              style={{ padding: '5px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}
            >
              Previous
            </Button>
            <span>Page {historyPage + 1}</span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={!hasNextHistoryPage}
              onClick={() => setHistoryPage((page) => page + 1)}
              style={{ padding: '5px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}
            >
              Next
            </Button>
          </div>
        </section>
      </div>
    </div>
    </div>
  )
}
