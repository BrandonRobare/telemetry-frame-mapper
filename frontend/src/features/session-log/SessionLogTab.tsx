import { useQuery } from '@tanstack/react-query'
import { get } from '../../shared/api/client'
import { useMapStore } from '../../shared/stores/mapStore'

interface SessionLogEntry {
  id: number
  session_id: number
  event_type: string
  photo_count: number | null
  coverage_pct: number | null
  message: string | null
  created_at: string
}

function useSessionLog(sessionId: number | null) {
  return useQuery<SessionLogEntry[]>({
    queryKey: ['session-log', sessionId],
    queryFn: () => get<SessionLogEntry[]>(`/session-log?session_id=${sessionId}`),
    enabled: sessionId !== null,
    refetchInterval: 10_000,
    staleTime: 8_000,
  })
}

const EVENT_BADGE: Record<string, React.CSSProperties> = {
  import_complete: { background: 'rgba(63,185,80,0.15)', color: '#3fb950', border: '1px solid rgba(63,185,80,0.3)' },
  import_error:    { background: 'rgba(248,81,73,0.15)', color: '#f85149', border: '1px solid rgba(248,81,73,0.3)' },
  coverage_run:    { background: 'rgba(88,166,255,0.15)', color: '#58a6ff', border: '1px solid rgba(88,166,255,0.3)' },
}

function EventBadge({ type }: { type: string }) {
  const style = EVENT_BADGE[type] ?? {
    background: 'var(--surface)',
    color: 'var(--text-muted)',
    border: '1px solid var(--border)',
  }
  return (
    <span
      className="text-xs rounded"
      style={{ padding: '2px 8px', whiteSpace: 'nowrap', fontFamily: 'inherit', ...style }}
    >
      {type.replace(/_/g, ' ')}
    </span>
  )
}

export default function SessionLogTab() {
  const { selectedSessionId } = useMapStore()
  const { data: entries, isLoading, error } = useSessionLog(selectedSessionId)

  if (selectedSessionId === null) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        <p>Select a session first.</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        <p>Loading log…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--danger, #f85149)' }}>
        <p>Failed to load session log.</p>
      </div>
    )
  }

  const sorted = (entries ?? [])
    .slice()
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())

  if (sorted.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        <p>No log entries yet.</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-auto" style={{ padding: 24 }}>
      <h2 className="text-sm font-semibold" style={{ color: 'var(--text)', marginBottom: 16 }}>
        Session Log
      </h2>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: 13,
          color: 'var(--text)',
        }}
      >
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border)' }}>
            {['Timestamp', 'Event', 'Photos', 'Coverage', 'Message'].map((h) => (
              <th
                key={h}
                className="text-left text-xs font-medium"
                style={{ padding: '6px 12px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((entry) => (
            <tr
              key={entry.id}
              style={{ borderBottom: '1px solid var(--border)' }}
            >
              <td style={{ padding: '8px 12px', whiteSpace: 'nowrap', color: 'var(--text-muted)' }}>
                {new Date(entry.created_at).toLocaleString()}
              </td>
              <td style={{ padding: '8px 12px' }}>
                <EventBadge type={entry.event_type} />
              </td>
              <td style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text-muted)' }}>
                {entry.photo_count ?? '—'}
              </td>
              <td style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text-muted)' }}>
                {entry.coverage_pct != null ? `${entry.coverage_pct.toFixed(1)}%` : '—'}
              </td>
              <td style={{ padding: '8px 12px', color: 'var(--text-muted)' }}>
                {entry.message ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
