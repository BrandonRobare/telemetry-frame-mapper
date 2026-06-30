import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get } from '../../shared/api/client'
import type { StorageStats, StorageFileItem, StorageFileList } from '../../types/api'
import { formatBytes } from './formatBytes'
import TabHeader from '../../shared/components/TabHeader'
import { useToast } from '../../shared/hooks/useToast'
import { Button } from '../../shared/components/Button'
import ConfirmDialog from '../../shared/components/ConfirmDialog'

function useStorageSummary() {
  return useQuery<StorageStats>({
    queryKey: ['storage-summary'],
    queryFn: () => get<StorageStats>('/storage/summary'),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

const DIRECTORIES = ['imports', 'processed', 'exports', 'data'] as const
type Directory = (typeof DIRECTORIES)[number]

function useStorageFiles(directory: Directory) {
  return useQuery<StorageFileList>({
    queryKey: ['storage-files', directory],
    queryFn: () => get<StorageFileList>(`/storage/files?directory=${directory}`),
  })
}

function FileBrowser() {
  const qc = useQueryClient()
  const addToast = useToast((s) => s.addToast)
  const [dir, setDir] = useState<Directory>('imports')
  const [deleting, setDeleting] = useState<string | null>(null)
  const [fileToDelete, setFileToDelete] = useState<StorageFileItem | null>(null)
  const { data, isLoading } = useStorageFiles(dir)

  async function handleDelete(file: StorageFileItem) {
    setDeleting(file.path)
    try {
      await del(`/storage/file?directory=${dir}&filename=${encodeURIComponent(file.name)}`)
      setFileToDelete(null)
    } catch (e) {
      addToast(`Couldn't delete ${file.name}: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
      return
    } finally {
      setDeleting(null)
    }
    qc.invalidateQueries({ queryKey: ['storage-files', dir] })
    qc.invalidateQueries({ queryKey: ['storage-summary'] })
  }

  return (
    <div style={{ marginTop: 20 }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        {DIRECTORIES.map((d) => (
          <button
            key={d}
            onClick={() => setDir(d)}
            style={{
              padding: '4px 12px', borderRadius: 'var(--radius-sm)', fontSize: 12,
              border: dir === d ? '1px solid var(--accent)' : '1px solid var(--border)',
              cursor: 'pointer',
              background: dir === d ? 'var(--accent-soft)' : 'var(--surface)',
              color: dir === d ? 'var(--accent-strong)' : 'var(--text-muted)',
              fontFamily: 'inherit',
            }}
          >
            {d}
          </button>
        ))}
      </div>
      {isLoading ? (
        <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>Loading…</div>
      ) : (data?.files ?? []).length === 0 ? (
        <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>No files in {dir}.</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
              <th style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)', fontWeight: 500 }}>Name</th>
              <th style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)', fontWeight: 500, textAlign: 'right' }}>Size</th>
              <th style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)', fontWeight: 500, textAlign: 'right' }}>Modified</th>
              <th style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)' }} />
            </tr>
          </thead>
          <tbody>
            {(data?.files ?? []).map((f) => (
              <tr
                key={f.path}
                style={{ borderBottom: '1px solid var(--border)', opacity: deleting === f.path ? 0.4 : 1 }}
              >
                <td style={{ padding: '5px 8px', color: 'var(--text)' }}>{f.name}</td>
                <td style={{ padding: '5px 8px', color: 'var(--text-muted)', textAlign: 'right' }}>
                  {formatBytes(f.size_bytes)}
                </td>
                <td style={{ padding: '5px 8px', color: 'var(--text-muted)', textAlign: 'right' }}>
                  {new Date(f.modified * 1000).toLocaleDateString()}
                </td>
                <td style={{ padding: '5px 8px', textAlign: 'right' }}>
                  <Button
                    type="button"
                    variant="danger"
                    size="sm"
                    onClick={() => setFileToDelete(f)}
                    loading={deleting === f.path}
                    disabled={deleting !== null}
                  >
                    Delete
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <ConfirmDialog
        open={fileToDelete !== null}
        title="Delete file?"
        description={
          <>
            Delete <strong>{fileToDelete?.name}</strong>? This cannot be undone.
          </>
        }
        confirmLabel="Delete file"
        danger
        loading={fileToDelete !== null && deleting === fileToDelete.path}
        onCancel={() => setFileToDelete(null)}
        onConfirm={() => { if (fileToDelete) void handleDelete(fileToDelete) }}
      />
    </div>
  )
}

// Categorical colors from the warm palette: terracotta / tan / sage / amber.
const DIR_META: Record<string, { label: string; color: string; description: string }> = {
  imports:   { label: 'Imports',   color: 'var(--accent)', description: 'Raw imported session folders' },
  processed: { label: 'Processed', color: 'var(--tan)', description: 'Thumbnails and COLMAP workspaces' },
  exports:   { label: 'Exports',   color: 'var(--sage)', description: 'WebODM CSV zips and GeoJSON files' },
  data:      { label: 'Data',      color: 'var(--warning-accent)', description: 'SQLite database and config files' },
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
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--danger)' }}>
        Couldn't load storage usage. Reload to try again.
      </div>
    )
  }

  const total = data.total_bytes || 1
  const entries = Object.entries(data.by_type) as [string, number][]

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <TabHeader
        title="Storage"
        description="Disk usage by category; browse and clean up files."
      />
      <div className="flex-1 overflow-y-auto p-6" style={{ color: 'var(--text)' }}>
      <div className="mx-auto" style={{ maxWidth: 600 }}>

        {/* Total */}
        <section
          className="p-5 flex flex-col gap-3"
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
          className="overflow-hidden"
          style={{ border: '1px solid var(--border)' }}
        >
          {entries.map(([key, bytes], i) => {
            const meta = DIR_META[key] ?? { label: key, color: 'var(--text-faint)', description: '' }
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

        <FileBrowser />
      </div>
    </div>
    </div>
  )
}
