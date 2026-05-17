import { useQuery } from '@tanstack/react-query'
import { get } from '../../shared/api/client'
import type { StorageStats } from '../../types/api'

function useStorageSummary() {
  return useQuery<StorageStats>({
    queryKey: ['storage-summary'],
    queryFn: () => get<StorageStats>('/storage/summary'),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

const DIR_META: Record<string, { label: string; color: string; description: string }> = {
  imports:   { label: 'Imports',   color: '#60a5fa', description: 'Raw imported session folders' },
  processed: { label: 'Processed', color: '#a78bfa', description: 'Thumbnails and COLMAP workspaces' },
  exports:   { label: 'Exports',   color: '#34d399', description: 'WebODM zips and GeoJSON files' },
  data:      { label: 'Data',      color: '#f59e0b', description: 'SQLite database and config' },
}

export default function StorageTab() {
  const { data, isLoading, error, dataUpdatedAt } = useStorageSummary()

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        Loading storage info…
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--danger, #f85149)' }}>
        Failed to load storage info.
      </div>
    )
  }

  const total = data.total_bytes || 1
  const entries = Object.entries(data.by_type) as [string, number][]

  return (
    <div className="flex-1 overflow-y-auto p-6" style={{ color: 'var(--text)' }}>
      <div className="mx-auto" style={{ maxWidth: 600 }}>

        {/* Total */}
        <section
          className="rounded-lg p-5 flex flex-col gap-3"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)', marginBottom: 20 }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <h2 className="text-base font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
              Disk Usage
            </h2>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Updated {new Date(dataUpdatedAt).toLocaleTimeString()}
            </span>
          </div>
          <p className="text-2xl font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
            {formatBytes(data.total_bytes)}
          </p>

          {/* Stacked bar */}
          <div style={{ display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', gap: 1 }}>
            {entries.map(([key, bytes]) => {
              const pct = (bytes / total) * 100
              const meta = DIR_META[key]
              if (!meta || pct < 0.5) return null
              return (
                <div
                  key={key}
                  title={`${meta.label}: ${formatBytes(bytes)} (${pct.toFixed(1)}%)`}
                  style={{ width: `${pct}%`, background: meta.color, transition: 'width 0.5s ease' }}
                />
              )
            })}
          </div>
        </section>

        {/* Per-directory breakdown */}
        <section
          className="rounded-lg overflow-hidden"
          style={{ border: '1px solid var(--border)' }}
        >
          {entries.map(([key, bytes], i) => {
            const meta = DIR_META[key] ?? { label: key, color: '#9ca3af', description: '' }
            const pct = total > 0 ? (bytes / total) * 100 : 0
            return (
              <div
                key={key}
                style={{
                  display: 'flex', flexDirection: 'column', gap: 6,
                  padding: '14px 16px',
                  background: 'var(--surface)',
                  borderBottom: i < entries.length - 1 ? '1px solid var(--border)' : 'none',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        width: 10, height: 10, borderRadius: '50%',
                        background: meta.color, display: 'inline-block',
                      }}
                    />
                    <span className="text-sm font-medium" style={{ color: 'var(--text)' }}>{meta.label}</span>
                    {meta.description && (
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{meta.description}</span>
                    )}
                  </div>
                  <span className="text-sm" style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>
                    {formatBytes(bytes)}
                  </span>
                </div>
                <div style={{ height: 4, borderRadius: 2, background: 'var(--border)', overflow: 'hidden' }}>
                  <div
                    style={{
                      height: '100%', borderRadius: 2,
                      background: meta.color, opacity: 0.7,
                      width: `${pct}%`, transition: 'width 0.5s ease',
                    }}
                  />
                </div>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {pct.toFixed(1)}% of total
                </span>
              </div>
            )
          })}
        </section>
      </div>
    </div>
  )
}
