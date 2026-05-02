import { useEffect } from 'react'
import { useSessions } from './useSessions'
import { useMapStore } from '../../shared/stores/mapStore'

interface SessionPickerProps {
  /** Called when the user clicks the empty-state "Import" prompt */
  onImport?: () => void
}

const SELECT_STYLE: React.CSSProperties = {
  background: 'var(--bg)',
  border: '1px solid var(--border)',
  borderRadius: 5,
  color: 'var(--text)',
  fontSize: 12,
  fontFamily: 'inherit',
  padding: '3px 8px',
  cursor: 'pointer',
  maxWidth: 220,
  height: 28,
}

export default function SessionPicker({ onImport }: SessionPickerProps) {
  const { data: sessions, isLoading } = useSessions()
  const { selectedSessionId, setSession } = useMapStore()

  // Auto-select the most recent session (index 0 — backend returns desc order)
  useEffect(() => {
    if (sessions && sessions.length > 0 && selectedSessionId === null) {
      setSession(sessions[0].id)
    }
  }, [sessions, selectedSessionId, setSession])

  if (isLoading) {
    return (
      <span className="text-xs" style={{ color: 'var(--text-muted)', padding: '0 8px' }}>
        Loading sessions…
      </span>
    )
  }

  if (!sessions || sessions.length === 0) {
    return (
      <button
        onClick={onImport}
        className="text-xs cursor-pointer border-none bg-transparent"
        style={{ color: 'var(--accent)', padding: '0 8px', fontFamily: 'inherit' }}
      >
        Import your first session →
      </button>
    )
  }

  return (
    <select
      value={selectedSessionId ?? ''}
      onChange={(e) => setSession(parseInt(e.target.value, 10))}
      style={SELECT_STYLE}
      title="Select active session"
    >
      {sessions.map((s) => {
        const date = s.imported_at
          ? new Date(s.imported_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
          : null
        return (
          <option key={s.id} value={s.id}>
            {s.name}{date ? ` — ${date}` : ''}
          </option>
        )
      })}
    </select>
  )
}
