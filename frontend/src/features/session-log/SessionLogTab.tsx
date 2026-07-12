import { useQuery } from '@tanstack/react-query'
import { get } from '../../shared/api/client'
import { useMapStore } from '../../shared/stores/mapStore'
import TabHeader from '../../shared/components/TabHeader'
import EmptyState from '../../shared/components/EmptyState'
import FlightEntriesSection from './FlightEntriesSection'
import { formatLogTimestamp } from './formatLogTimestamp'

interface SessionLogEntry {
  id: number
  session_id: number
  event_type: string
  photo_count: number | null
  coverage_pct: number | null
  message: string | null
  timestamp: string | null
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
  import_complete: { background: 'var(--success-soft)', color: 'var(--success)' },
  import_error:    { background: 'var(--danger-soft)',  color: 'var(--danger)' },
  coverage_run:    { background: 'var(--accent-soft)',  color: 'var(--accent-strong)' },
}

function EventBadge({ type }: { type: string }) {
  const style = EVENT_BADGE[type] ?? {
    background: 'var(--surface-2)',
    color: 'var(--text-muted)',
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
  const { selectedSessionId, setRequestedTab } = useMapStore()
  const { data: entries, isLoading, error } = useSessionLog(selectedSessionId)

  const sorted = (entries ?? [])
    .slice()
    .sort((a, b) => new Date(b.timestamp ?? '').getTime() - new Date(a.timestamp ?? '').getTime())

  let body: React.ReactNode
  if (selectedSessionId === null) {
    body = (
      <EmptyState
        title="No session selected"
        description="Choose a session to see its timeline of imports, coverage runs, and jobs."
        actionLabel="Open Overview"
        onAction={() => setRequestedTab('overview')}
      />
    )
  } else if (isLoading) {
    body = (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        <p>Loading log…</p>
      </div>
    )
  } else if (error) {
    body = (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--danger, #f85149)' }}>
        <p>Failed to load session log.</p>
      </div>
    )
  } else if (sorted.length === 0) {
    body = (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        <p>No log entries yet.</p>
      </div>
    )
  } else {
    body = (
      <div className="flex-1 overflow-auto" style={{ padding: 24 }}>
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
                {formatLogTimestamp(entry.timestamp)}
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

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <TabHeader
        title="Session Log"
        description="A timeline of imports, coverage runs, and jobs for this session."
      />
      {selectedSessionId !== null && <FlightEntriesSection sessionId={selectedSessionId} />}
      {body}
    </div>
  )
}
