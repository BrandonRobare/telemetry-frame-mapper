import { useQuery } from '@tanstack/react-query'
import { get } from '../../shared/api/client'
import type { Job } from '../../types/api'

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

const STATUS_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  pending:        { bg: '#1e3a5f', text: '#93c5fd', label: 'Pending' },
  running_colmap: { bg: '#78350f', text: '#fcd34d', label: 'COLMAP' },
  running_gsplat: { bg: '#4c1d95', text: '#c4b5fd', label: 'Gaussian' },
  complete:       { bg: '#14532d', text: '#86efac', label: 'Complete' },
  failed:         { bg: '#450a0a', text: '#fca5a5', label: 'Failed' },
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
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        Loading jobs…
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
                return (
                  <div
                    key={job.id}
                    style={{
                      background: 'var(--surface)',
                      border: '1px solid rgba(167,139,250,0.35)',
                      borderRadius: 8, padding: '14px 16px',
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
                    <div style={{ height: 4, borderRadius: 2, background: 'var(--border)', overflow: 'hidden' }}>
                      <div
                        style={{
                          height: '100%', borderRadius: 2,
                          background: 'linear-gradient(90deg, #7c3aed, #a78bfa)',
                          width: `${job.progress_pct}%`,
                          transition: 'width 0.5s ease',
                        }}
                      />
                    </div>
                    <p className="text-xs" style={{ color: 'var(--text-muted)', marginTop: 6, marginBottom: 0 }}>
                      {job.progress_pct.toFixed(1)}% · {job.step || 'Initializing…'}
                    </p>
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
  )
}
