import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../../shared/api/client'
import type { SessionSearchResult, SessionSearchSource } from '../../types/api'
import { SEARCH_SOURCES, buildSessionSearchPath, sourceLabel } from './searchUtils'

interface Props {
  onSelect: (session: SessionSearchResult) => void
}

export default function SessionSearch({ onSelect }: Props) {
  const [query, setQuery] = useState('')
  const [source, setSource] = useState<SessionSearchSource | ''>('')
  const [open, setOpen] = useState(false)
  const trimmed = query.trim()
  const search = useQuery<SessionSearchResult[]>({
    queryKey: ['session-search', trimmed, source],
    queryFn: () => get<SessionSearchResult[]>(buildSessionSearchPath(trimmed, source)),
    enabled: trimmed.length >= 2,
    staleTime: 15_000,
  })

  return (
    <div className="relative flex items-center gap-1">
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => setOpen(true)}
        placeholder="Search sessions"
        aria-label="Search all sessions"
        style={{
          width: 140,
          height: 28,
          padding: '3px 7px',
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--text)',
          fontSize: 12,
          fontFamily: 'inherit',
        }}
      />
      <select
        value={source}
        onChange={(event) => setSource(event.target.value as SessionSearchSource | '')}
        aria-label="Search source"
        title="Filter search results"
        style={{
          height: 28,
          padding: '2px 4px',
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--text-muted)',
          fontSize: 11,
          fontFamily: 'inherit',
        }}
      >
        {SEARCH_SOURCES.map((item) => <option key={item} value={item}>{item || 'All'}</option>)}
      </select>
      {open && trimmed.length >= 2 && (
        <div
          role="listbox"
          aria-label="Session search results"
          className="absolute"
          style={{ top: 34, right: 0, width: 320, zIndex: 50, background: 'var(--surface)', border: '1px solid var(--border-strong)', boxShadow: 'var(--shadow-2)', padding: 4 }}
        >
          {search.isLoading && <div style={{ padding: 8, fontSize: 12, color: 'var(--text-muted)' }}>Searching…</div>}
          {search.isError && <div style={{ padding: 8, fontSize: 12, color: 'var(--danger)' }}>Search failed</div>}
          {search.data?.length === 0 && <div style={{ padding: 8, fontSize: 12, color: 'var(--text-muted)' }}>No matching sessions</div>}
          {search.data?.map((result) => (
            <button
              key={result.id}
              role="option"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => { onSelect(result); setOpen(false); setQuery('') }}
              className="w-full text-left cursor-pointer border-none"
              style={{ padding: '6px 8px', background: 'transparent', color: 'var(--text)', fontFamily: 'inherit' }}
              onMouseEnter={(event) => { event.currentTarget.style.background = 'var(--surface-2)' }}
              onMouseLeave={(event) => { event.currentTarget.style.background = 'transparent' }}
            >
              <div style={{ fontSize: 12, fontWeight: 600 }}>{result.name}</div>
              {result.matches.map((match, index) => (
                <div key={`${match.source}-${index}`} style={{ marginTop: 2, fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  <span style={{ color: 'var(--accent-strong)' }}>{sourceLabel(match.source)}:</span> {match.snippet}
                </div>
              ))}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
