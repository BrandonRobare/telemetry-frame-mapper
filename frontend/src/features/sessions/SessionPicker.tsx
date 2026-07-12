import { useEffect, useState } from 'react'
import { useSessions } from './useSessions'
import { useMapStore } from '../../shared/stores/mapStore'
import { Skeleton } from '../../shared/components/Skeleton'
import { collectTags, filterSessionsByTag } from './sessionTags'

interface SessionPickerProps {
  /** Called when the user clicks the empty-state "Import" prompt */
  onImport?: () => void
  /** The selected project ID; sessions will be scoped to this project */
  projectId: number | null
}

const SELECT_STYLE: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--text)',
  fontSize: 12,
  fontFamily: 'inherit',
  padding: '3px 8px',
  cursor: 'pointer',
  maxWidth: 220,
  height: 28,
}

export default function SessionPicker({ onImport, projectId }: SessionPickerProps) {
  const { data: sessions, isLoading } = useSessions(projectId)
  const { selectedSessionId, setSession } = useMapStore()
  const [tagFilter, setTagFilter] = useState<string | null>(null)

  const allTags = collectTags(sessions ?? [])
  // A stale filter (tag no longer on any session) shows everything.
  const activeFilter = tagFilter !== null && allTags.includes(tagFilter) ? tagFilter : null
  const visibleSessions = filterSessionsByTag(sessions ?? [], activeFilter)

  // Auto-select the most recent session (index 0 — backend returns desc order),
  // or the first match when the current selection is filtered out.
  useEffect(() => {
    if (visibleSessions.length === 0) return
    if (selectedSessionId === null || !visibleSessions.some((s) => s.id === selectedSessionId)) {
      setSession(visibleSessions[0].id)
    }
  }, [visibleSessions, selectedSessionId, setSession])

  if (isLoading) {
    return (
      <div style={{ padding: '0 8px' }}>
        <Skeleton width={150} height={20} radius="var(--radius-sm)" />
      </div>
    )
  }

  if (!sessions || sessions.length === 0) {
    return (
      <button
        onClick={onImport}
        className="text-xs cursor-pointer border-none bg-transparent"
        style={{ color: 'var(--accent-strong)', padding: '0 8px', fontFamily: 'inherit' }}
      >
        Import your first session →
      </button>
    )
  }

  return (
    <span className="inline-flex items-center gap-1.5">
      <select
        value={selectedSessionId ?? ''}
        onChange={(e) => setSession(parseInt(e.target.value, 10))}
        style={SELECT_STYLE}
        title="Select active session"
      >
        {visibleSessions.map((s) => {
          const date = s.imported_at
            ? new Date(s.imported_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
            : null
          return (
            <option key={s.id} value={s.id}>
              {s.name}{date ? `, ${date}` : ''}
            </option>
          )
        })}
      </select>
      {allTags.length > 0 && (
        <select
          value={activeFilter ?? ''}
          onChange={(e) => setTagFilter(e.target.value || null)}
          style={{ ...SELECT_STYLE, maxWidth: 130 }}
          title="Filter sessions by tag"
          aria-label="Filter sessions by tag"
        >
          <option value="">All tags</option>
          {allTags.map((tag) => (
            <option key={tag} value={tag}>
              #{tag}
            </option>
          ))}
        </select>
      )}
    </span>
  )
}
