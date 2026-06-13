import { useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import type { Session, CoverageResult } from '../../types/api'
import { useMapStore } from '../../shared/stores/mapStore'
import { get } from '../../shared/api/client'
import { Skeleton } from '../../shared/components/Skeleton'

interface Props {
  session: Session | undefined
  coverage: CoverageResult | null | undefined
  frameCount: number
  isLoading?: boolean
}

function StatCard({ label, value, color }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <motion.div
      whileHover={{ y: -2 }}
      transition={{ duration: 0.15, ease: [0.22, 1, 0.36, 1] }}
      className="p-2"
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
      }}
    >
      <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div className="text-base font-semibold mt-0.5" style={{ color: color ?? 'var(--accent-strong)' }}>
        {value}
      </div>
    </motion.div>
  )
}

function SidebarSkeleton() {
  return (
    <aside
      className="shrink-0 flex flex-col gap-3"
      style={{ width: 200, background: 'var(--surface)', borderLeft: '1px solid var(--border)', padding: 12 }}
    >
      <Skeleton width="60%" height={10} />
      <Skeleton width="80%" height={14} />
      <div className="grid grid-cols-2 gap-1.5" style={{ marginTop: 4 }}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 8 }}>
            <Skeleton width="70%" height={8} />
            <div style={{ height: 6 }} />
            <Skeleton width="50%" height={12} />
          </div>
        ))}
      </div>
      <Skeleton width="100%" height={6} radius="999px" />
      <Skeleton width="100%" height={32} radius="var(--radius-sm)" style={{ marginTop: 'auto' }} />
    </aside>
  )
}

export default function SessionSidebar({ session, coverage, frameCount, isLoading }: Props) {
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

  if (isLoading && !session) {
    return <SidebarSkeleton />
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
          <div className="rounded-full h-1" style={{ background: 'var(--surface-2)' }}>
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{ width: `${covPct}%`, background: 'var(--sage)' }}
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
        className="m-3 rounded text-sm cursor-pointer border-none transition-all duration-150 active:scale-[0.98]"
        style={{
          padding: '8px',
          background: coverageMutation.isPending ? 'var(--border-strong)' : 'var(--accent-strong)',
          color: '#FFFDF7',
          fontFamily: 'inherit',
          opacity: coverageMutation.isPending ? 0.7 : 1,
        }}
      >
        {coverageMutation.isPending ? 'Running…' : 'Run Coverage Analysis'}
      </button>
    </aside>
  )
}
