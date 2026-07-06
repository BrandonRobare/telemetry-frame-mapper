import { useState } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { del, get, post } from '../../shared/api/client'
import type { StorageStats, StorageFileItem, StorageFileList, PolicyResult } from '../../types/api'
import { formatBytes } from './formatBytes'
import TabHeader from '../../shared/components/TabHeader'
import { Button } from '../../shared/components/Button'
import { useToast } from '../../shared/hooks/useToast'
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

// ---- Lifecycle Policy Panel ----

interface PolicyRuleInput {
  target: string
  age_days: number | null
  disk_pct: number | null
}

const TARGETS = [
  { value: 'raw_frames', label: 'Raw Frames (imports/)' },
  { value: 'colmap_intermediates', label: 'COLMAP Intermediates (processed/*/colmap/)' },
  { value: 'reconstruction_artifacts', label: 'Reconstruction Artifacts (splats, meshes, LAS)' },
]

function LifecyclePolicy() {
  const { addToast } = useToast()
  const qc = useQueryClient()

  const [rules, setRules] = useState<PolicyRuleInput[]>([
    { target: 'raw_frames', age_days: 30, disk_pct: null },
  ])
  const [result, setResult] = useState<PolicyResult | null>(null)
  const [showConfirm, setShowConfirm] = useState(false)

  const policyMutation = useMutation({
    mutationFn: (execute: boolean) =>
      post<PolicyResult>('/storage/apply-policy', { rules, execute }),
    onSuccess: (data) => {
      setResult(data)
      if (data.mode === 'execute') {
        addToast(
          `Policy applied: ${data.summary.removed_items ?? 0} removed, ${data.summary.failed_items ?? 0} failed`,
          'success',
        )
        qc.invalidateQueries({ queryKey: ['storage-summary'] })
        qc.invalidateQueries({ queryKey: ['storage-files'] })
      }
    },
    onError: (err: Error) => addToast(`Policy error: ${err.message}`, 'error'),
  })

  function addRule() {
    setRules((prev) => [...prev, { target: 'raw_frames', age_days: 30, disk_pct: null }])
  }

  function removeRule(index: number) {
    setRules((prev) => prev.filter((_, i) => i !== index))
  }

  function updateRule(index: number, patch: Partial<PolicyRuleInput>) {
    setRules((prev) =>
      prev.map((r, i) => (i === index ? { ...r, ...patch } : r))
    )
  }

  const totalSize = result ? formatBytes(result.summary.total_bytes) : '--'

  return (
    <section
      className="p-5 flex flex-col gap-4"
      style={{ background: 'var(--surface)', border: '1px solid var(--border)', marginTop: 20 }}
    >
      <div>
        <h2 className="text-base font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
          Lifecycle Policy
        </h2>
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)', margin: '4px 0 0' }}>
          Define retention rules by age or disk pressure. Dry-run first to preview
          before executing.
        </p>
      </div>

      {rules.map((rule, i) => (
        <div
          key={i}
          className="flex flex-col gap-2 p-3"
          style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={rule.target}
              onChange={(e) => updateRule(i, { target: e.target.value })}
              style={{
                padding: '4px 8px', fontSize: 12, borderRadius: 'var(--radius-sm)',
                background: 'var(--surface)', color: 'var(--text)', border: '1px solid var(--border)',
              }}
            >
              {TARGETS.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>

            <label className="text-xs" style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <input
                type="radio"
                checked={rule.age_days !== null}
                onChange={() => updateRule(i, { age_days: 30, disk_pct: null })}
              />
              Age (days)
            </label>
            <input
              type="number"
              min={0}
              max={365}
              value={rule.age_days ?? ''}
              disabled={rule.age_days === null}
              onChange={(e) => updateRule(i, { age_days: e.target.value ? Number(e.target.value) : null, disk_pct: null })}
              style={{
                width: 64, padding: '4px 6px', fontSize: 12,
                borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)',
                background: 'var(--surface)', color: 'var(--text)',
              }}
            />

            <label className="text-xs" style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <input
                type="radio"
                checked={rule.disk_pct !== null}
                onChange={() => updateRule(i, { age_days: null, disk_pct: 80 })}
              />
              Disk %
            </label>
            <input
              type="number"
              min={1}
              max={99}
              value={rule.disk_pct ?? ''}
              disabled={rule.disk_pct === null}
              onChange={(e) => updateRule(i, { age_days: null, disk_pct: e.target.value ? Number(e.target.value) : null })}
              style={{
                width: 56, padding: '4px 6px', fontSize: 12,
                borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)',
                background: 'var(--surface)', color: 'var(--text)',
              }}
            />

            {rules.length > 1 && (
              <Button variant="danger" size="sm" onClick={() => removeRule(i)} style={{ fontSize: 11, marginLeft: 'auto' }}>
                Remove
              </Button>
            )}
          </div>
        </div>
      ))}

      <div className="flex items-center gap-2 flex-wrap">
        <Button variant="ghost" size="sm" onClick={addRule} style={{ fontSize: 12 }}>
          + Add Rule
        </Button>

        <Button
          variant="primary"
          size="sm"
          onClick={() => policyMutation.mutate(false)}
          disabled={policyMutation.isPending}
          style={{ fontSize: 12, marginLeft: 'auto' }}
        >
          {policyMutation.isPending ? 'Running...' : 'Dry Run'}
        </Button>

        <Button
          variant="danger"
          size="sm"
          onClick={() => setShowConfirm(true)}
          disabled={policyMutation.isPending || result === null}
          style={{ fontSize: 12 }}
        >
          Execute
        </Button>
      </div>

      {policyMutation.isPending && (
        <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Evaluating policy...</div>
      )}

      {result && !policyMutation.isPending && (
        <div
          className="p-3 flex flex-col gap-2 text-xs"
          style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
        >
          <div style={{ color: 'var(--text)', fontWeight: 600 }}>
            {result.mode === 'dry-run' ? 'Dry Run Result' : 'Execute Result'}
          </div>
          <div style={{ color: 'var(--text-muted)' }}>
            {result.summary.total_items} candidates · {totalSize}
            {result.summary.actions && (
              <span> · {Object.entries(result.summary.actions).map(([k, v]) => `${v} ${k}`).join(', ')}</span>
            )}
          </div>

          {result.candidates.length > 0 && (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                  <th style={{ padding: '3px 6px', borderBottom: '1px solid var(--border)', fontWeight: 500 }}>Path</th>
                  <th style={{ padding: '3px 6px', borderBottom: '1px solid var(--border)', fontWeight: 500, textAlign: 'right' }}>Size</th>
                  <th style={{ padding: '3px 6px', borderBottom: '1px solid var(--border)', fontWeight: 500 }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {result.candidates.slice(0, 20).map((c, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '3px 6px', color: 'var(--text)', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.path}>
                      {c.path}
                    </td>
                    <td style={{ padding: '3px 6px', color: 'var(--text)', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                      {formatBytes(c.bytes)}
                    </td>
                    <td style={{ padding: '3px 6px', color: c.action === 'delete' ? 'var(--danger)' : 'var(--warning-accent)' }}>
                      {c.action}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {result.candidates.length > 20 && (
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
              ...and {result.candidates.length - 20} more candidates
            </div>
          )}

          {result.executed && (
            <div style={{ color: 'var(--success)', marginTop: 4 }}>
              Removed: {result.executed.removed.length} files
              {result.executed.failed.length > 0 && (
                <span style={{ color: 'var(--danger)' }}>
                  {' '}Failed: {result.executed.failed.length}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={showConfirm}
        title="Execute lifecycle policy?"
        description={
          <>
            This will {result?.summary.actions ? Object.entries(result.summary.actions).map(([k, v]) => `${k} ${v} ${k === 'delete' ? 'files/directories' : 'items'}`).join(', ') : 'process'}{' '}
            ({totalSize}). This action <strong>cannot be undone</strong>.
          </>
        }
        confirmLabel="Execute policy"
        danger
        loading={policyMutation.isPending}
        onCancel={() => setShowConfirm(false)}
        onConfirm={() => {
          setShowConfirm(false)
          policyMutation.mutate(true)
        }}
      />
    </section>
  )
}

// ---- File Browser ----

function FileBrowser() {
  const qc = useQueryClient()
  const { addToast } = useToast()
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
          <Button
            type="button"
            variant={dir === d ? 'primary' : 'ghost'}
            size="sm"
            key={d}
            onClick={() => setDir(d)}
            style={{
              padding: '4px 12px', borderRadius: 'var(--radius-sm)', fontSize: 12,
            }}
          >
            {d}
          </Button>
        ))}
      </div>
      {isLoading ? (
        <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>Loading...</div>
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
                    style={{
                      borderRadius: 'var(--radius-sm)', fontSize: 11,
                      padding: '2px 8px',
                    }}
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
        Loading storage info...
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

          {data.by_session.length > 0 && (
            <section
              className="overflow-hidden"
              style={{ border: '1px solid var(--border)', marginTop: 20 }}
            >
              <div
                style={{
                  padding: '12px 16px',
                  background: 'var(--surface)',
                  borderBottom: '1px solid var(--border)',
                }}
              >
                <h2 className="text-base font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
                  Usage by session
                </h2>
                <p className="text-xs" style={{ color: 'var(--text-muted)', margin: '4px 0 0' }}>
                  Processed session folders ranked by disk usage.
                </p>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                    <th style={{ padding: '6px 12px', borderBottom: '1px solid var(--border)', fontWeight: 500 }}>
                      Session
                    </th>
                    <th style={{ padding: '6px 12px', borderBottom: '1px solid var(--border)', fontWeight: 500, textAlign: 'right' }}>
                      Size
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_session
                    .slice()
                    .sort((a, b) => b.bytes - a.bytes)
                    .map((session) => (
                      <tr key={session.session_id} style={{ borderBottom: '1px solid var(--border)' }}>
                        <td style={{ padding: '6px 12px', color: 'var(--text)' }}>
                          Session {session.session_id}
                        </td>
                        <td style={{ padding: '6px 12px', color: 'var(--text)', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                          {formatBytes(session.bytes)}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </section>
          )}

          <LifecyclePolicy />

          <FileBrowser />
        </div>
      </div>
    </div>
  )
}