import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../../shared/api/client'
import { formatEta } from '../../shared/time'
import type { Job, SystemResources } from '../../types/api'
import { SkeletonRow } from '../../shared/components/Skeleton'

function useAllJobs() {
  return useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: () => get<Job[]>('/jobs/'),
    refetchInterval: (query) => {
      const jobs = query.state.data ?? []
      const hasRunning = jobs.some((j) =>
        ['pending', 'running_colmap', 'running_gsplat'].includes(j.status)
      )
      return hasRunning ? 3000 : 30_000
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
      <span style={{ marginLeft: 'auto' }}>Disk {diskPct}% used</span>
    </div>
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
  const { data } = useReconstructionLog(recId, open && isActive)
  const lines = data?.lines ?? []

  return (
    <div style={{ marginTop: 6 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          fontSize: 11, color: 'var(--text-muted)', fontFamily: 'inherit',
          padding: 0,
        }}
      >
        {open ? '▾' : '▸'} {open ? 'Hide' : 'Show'} log ({lines.length} lines)
      </button>
      {open && (
        <div
          style={{
            marginTop: 4, padding: '6px 8px', borderRadius: 'var(--radius-sm)',
            background: 'var(--surface-2)', maxHeight: 180, overflowY: 'auto',
            fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text)',
            border: '1px solid var(--border)',
          }}
        >
          {lines.length === 0 ? (
            <span style={{ color: 'var(--text-muted)' }}>No log entries yet.</span>
          ) : (
            lines.map((line, i) => <div key={`${i}-${line.slice(0, 8)}`}>{line}</div>)
          )}
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

function formatDuration(start: string, end: string | null): string {
  const startMs = new Date(start).getTime()
  const endMs = end ? new Date(end).getTime() : Date.now()
  const sec = Math.round((endMs - startMs) / 1000)
  if (sec < 60) return `${sec}s`
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
}

export default function JobsTab() {
  const { data: jobs, isLoading } = useAllJobs()

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

  const list = jobs ?? []

  if (list.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        No jobs yet. Start a reconstruction from the Reconstruct tab.
      </div>
    )
  }

  const running = list.filter((j) =>
    ['pending', 'running_colmap', 'running_gsplat'].includes(j.status)
  )
  const done = list.filter((j) => !['pending', 'running_colmap', 'running_gsplat'].includes(j.status))

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <ResourceBar />
      <div className="flex-1 overflow-y-auto p-6" style={{ color: 'var(--text)' }}>
        <div className="mx-auto" style={{ maxWidth: 800 }}>

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
                      <span
                        className="text-xs rounded"
                        style={{ padding: '2px 8px', background: s.bg, color: s.text }}
                      >
                        {s.label}
                      </span>
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

        <section>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text)', marginBottom: 12 }}>
            History
          </h2>
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
                      <span
                        className="text-xs rounded"
                        style={{ padding: '2px 7px', background: s.bg, color: s.text }}
                      >
                        {s.label}
                      </span>
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
        </section>
      </div>
    </div>
    </div>
  )
}
