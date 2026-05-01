import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { Session, CoverageResult } from '../../types/api'
import { useMapStore } from '../../shared/stores/mapStore'
import { get } from '../../shared/api/client'

interface Props {
  session: Session | undefined
  coverage: CoverageResult | null | undefined
  frameCount: number
}

function StatCard({ label, value, color }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <div className="rounded p-2" style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
      <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div className="text-base font-semibold mt-0.5" style={{ color: color ?? 'var(--accent)' }}>
        {value}
      </div>
    </div>
  )
}

export default function SessionSidebar({ session, coverage, frameCount }: Props) {
  const { sidebarOpen, toggleSidebar, selectedSessionId } = useMapStore()
  const queryClient = useQueryClient()

  const coverageMutation = useMutation({
    mutationFn: () => get(`/coverage/run?session_id=${selectedSessionId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['coverage', selectedSessionId] }),
  })

  if (!sidebarOpen) {
    return (
      <button
        onClick={toggleSidebar}
        className="shrink-0 flex items-center justify-center cursor-pointer border-none"
        style={{ width: 20, background: 'var(--surface)', borderLeft: '1px solid var(--border)', color: 'var(--text-muted)' }}
        title="Expand sidebar"
      >
        ‹
      </button>
    )
  }

  if (!session) {
    return (
      <aside
        className="shrink-0 flex flex-col items-center justify-center gap-2"
        style={{ width: 200, background: 'var(--surface)', borderLeft: '1px solid var(--border)', padding: 16 }}
      >
        <p className="text-sm text-center" style={{ color: 'var(--text-muted)' }}>
          No session selected
        </p>
        <p className="text-xs text-center" style={{ color: 'var(--text-muted)' }}>
          Import a flight to get started.
        </p>
      </aside>
    )
  }

  const covPct = coverage?.coverage_pct ?? null
  const importedAgo = session.imported_at
    ? new Date(session.imported_at).toLocaleDateString()
    : '—'

  return (
    <aside
      className="shrink-0 flex flex-col overflow-y-auto"
      style={{ width: 200, background: 'var(--surface)', borderLeft: '1px solid var(--border)' }}
    >
      {/* Session header */}
      <div className="p-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="text-xs uppercase tracking-wide mb-2" style={{ color: 'var(--text-muted)' }}>
          Session
        </div>
        <div className="text-sm font-semibold" style={{ color: 'var(--text)' }}>{session.name}</div>
        <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>Imported {importedAgo}</div>
      </div>

      {/* Stats grid */}
      <div className="p-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="grid grid-cols-2 gap-1.5">
          <StatCard label="Frames" value={frameCount} />
          <StatCard label="Usable" value={session.usable_count} color="var(--success)" />
          <StatCard label="Photos" value={session.photo_count} />
          <StatCard label="Coverage" value={covPct !== null ? `${covPct.toFixed(0)}%` : '—'} color="var(--success)" />
        </div>
      </div>

      {/* Coverage bar */}
      {covPct !== null && (
        <div className="px-3 py-2" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="flex justify-between text-xs mb-1">
            <span style={{ color: 'var(--text-muted)' }}>Coverage</span>
            <span style={{ color: 'var(--success)' }}>{covPct.toFixed(0)}%</span>
          </div>
          <div className="rounded-full h-1" style={{ background: 'var(--border)' }}>
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{ width: `${covPct}%`, background: 'linear-gradient(90deg, var(--success), #22c55e)' }}
            />
          </div>
        </div>
      )}

      {/* Quality flags */}
      <div className="px-3 py-2 flex-1" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="text-xs uppercase tracking-wide mb-2" style={{ color: 'var(--text-muted)' }}>
          Quality Flags
        </div>
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <span style={{ color: 'var(--success)' }}>● Good</span>
            <span style={{ color: 'var(--text)' }}>{session.usable_count}</span>
          </div>
          <div className="flex justify-between text-xs">
            <span style={{ color: 'var(--warning)' }}>● Blurry/Dark</span>
            <span style={{ color: 'var(--text)' }}>{Math.max(0, session.photo_count - session.usable_count)}</span>
          </div>
        </div>
      </div>

      {/* CTA */}
      <button
        onClick={() => coverageMutation.mutate()}
        disabled={coverageMutation.isPending}
        className="m-3 rounded text-sm cursor-pointer border-none"
        style={{
          padding: '8px',
          background: coverageMutation.isPending ? 'var(--border)' : 'var(--accent)',
          color: '#fff',
          fontFamily: 'inherit',
          opacity: coverageMutation.isPending ? 0.7 : 1,
        }}
      >
        {coverageMutation.isPending ? 'Running…' : 'Run Coverage Analysis'}
      </button>
    </aside>
  )
}
