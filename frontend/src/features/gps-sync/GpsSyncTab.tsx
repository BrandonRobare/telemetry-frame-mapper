import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useMapStore } from '../../shared/stores/mapStore'
import { useApplyFlightSync } from '../../shared/api/mutations'
import { useToast } from '../../shared/hooks/useToast'
import { Button } from '../../shared/components/Button'
import TabHeader from '../../shared/components/TabHeader'
import EmptyState from '../../shared/components/EmptyState'
import InfoHint from '../../shared/components/InfoHint'
import { get } from '../../shared/api/client'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

interface MatchPreviewRow {
  image_id: number
  filename: string
  matched_timestamp: number | null
  delta_s: number | null
  adjusted_timestamp: number
  interpolation_ratio: number
  interpolated: boolean
}

interface OffsetPreviewRow {
  offset_s: number
  matched: number
  total: number
  mean_abs_delta_s: number | null
}

export default function GpsSyncTab() {
  const { selectedSessionId, setRequestedTab } = useMapStore()
  const { addToast } = useToast()
  const applySync = useApplyFlightSync()

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSuccess, setUploadSuccess] = useState(false)
  const [previewEnabled, setPreviewEnabled] = useState(false)
  const [offsetS, setOffsetS] = useState(0)
  const [toleranceS, setToleranceS] = useState(2)

  const syncParams = `session_id=${selectedSessionId}&offset_s=${offsetS}&tolerance_s=${toleranceS}`

  const matchPreviewQuery = useQuery({
    queryKey: ['match-preview', selectedSessionId, offsetS, toleranceS],
    queryFn: () => get<MatchPreviewRow[]>(`/flight-logs/match-preview?${syncParams}`),
    enabled: previewEnabled && selectedSessionId !== null,
  })

  const offsetPreviewQuery = useQuery({
    queryKey: ['offset-preview', selectedSessionId, offsetS, toleranceS],
    queryFn: () =>
      get<OffsetPreviewRow[]>(`/flight-logs/offset-preview?${syncParams}&window_s=10&step_s=1`),
    enabled: previewEnabled && selectedSessionId !== null,
  })

  const matches = matchPreviewQuery.data ?? []
  const hasMatches = matches.length > 0

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || selectedSessionId === null) return

    setUploading(true)
    setUploadError(null)
    setUploadSuccess(false)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch(`${BASE_URL}/flight-logs/upload?session_id=${selectedSessionId}`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `Upload failed (${res.status})`)
      }
      setUploadSuccess(true)
      setPreviewEnabled(true)
      matchPreviewQuery.refetch()
      offsetPreviewQuery.refetch()
      addToast('Flight log uploaded', 'success')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Upload failed'
      setUploadError(msg)
      addToast(msg, 'error')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  if (selectedSessionId === null) {
    return (
      <EmptyState
        title="No session selected"
        description="Choose a session, then upload its flight log (CSV) to align frames by timestamp."
        actionLabel="Open Overview"
        onAction={() => setRequestedTab('overview')}
      />
    )
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <TabHeader
        title="GPS Sync"
        description="Align frames to a DJI flight log by timestamp."
        nextTab="review"
        nextLabel="Review"
      />
      <div
        className="flex-1 overflow-y-auto"
        style={{ padding: '24px 32px', background: 'var(--bg)', color: 'var(--text)' }}
      >
        <section
          className="mb-6"
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            padding: '16px 20px',
          }}
        >
          <h3 className="text-sm font-medium mb-3" style={{ color: 'var(--text)' }}>
            Flight Log
          </h3>
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              disabled={uploading}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploading ? 'Uploading…' : 'Upload Flight Log (CSV)'}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={handleFileChange}
            />
            {uploadSuccess && !uploadError && (
              <span className="text-xs" style={{ color: 'var(--success)' }}>
                Uploaded successfully
              </span>
            )}
            {uploadError && (
              <span className="text-xs" style={{ color: 'var(--danger)' }}>
                {uploadError}
              </span>
            )}
          </div>
        </section>

        {previewEnabled && (
          <section
            className="mb-6"
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              padding: '16px 20px',
            }}
          >
            <h3 className="text-sm font-medium mb-3" style={{ color: 'var(--text)' }}>
              Offset Tuning
            </h3>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Time offset (sec)
                <input
                  type="number"
                  step={0.1}
                  value={offsetS}
                  onChange={(e) => setOffsetS(Number(e.target.value))}
                  className="mt-1 w-full px-2 py-1 text-sm"
                  style={{
                    background: 'var(--bg)',
                    color: 'var(--text)',
                    border: '1px solid var(--border)',
                  }}
                />
                <span className="mt-1 block">
                  Positive values shift image timestamps later before matching the log.
                </span>
              </label>
              <label className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Match tolerance (sec)
                <input
                  type="number"
                  min={0}
                  step={0.1}
                  value={toleranceS}
                  onChange={(e) => setToleranceS(Math.max(0, Number(e.target.value)))}
                  className="mt-1 w-full px-2 py-1 text-sm"
                  style={{
                    background: 'var(--bg)',
                    color: 'var(--text)',
                    border: '1px solid var(--border)',
                  }}
                />
                <span className="mt-1 block">
                  Used for points near the start/end of the log and for previewing sample spacing.
                </span>
              </label>
            </div>

            {offsetPreviewQuery.isSuccess && offsetPreviewQuery.data.length > 0 && (
              <div className="mt-4">
                <div
                  className="mb-2 flex items-center gap-2 text-xs"
                  style={{ color: 'var(--text-muted)' }}
                >
                  <span>Offset preview</span>
                  <InfoHint text="Bars show how many images would sync for nearby offsets. Use the peak with the smallest mean Δt." />
                </div>
                <div className="flex h-24 items-end gap-1" aria-label="Offset preview graph">
                  {offsetPreviewQuery.data.map((row) => {
                    const height = row.total > 0 ? Math.max(4, (row.matched / row.total) * 96) : 4
                    const active = Math.abs(row.offset_s - offsetS) < 0.001
                    return (
                      <button
                        key={row.offset_s}
                        type="button"
                        title={`offset ${row.offset_s}s: ${row.matched}/${row.total} matches, mean Δt ${row.mean_abs_delta_s ?? 'n/a'}s`}
                        onClick={() => setOffsetS(row.offset_s)}
                        className="flex-1"
                        style={{
                          height,
                          minWidth: 8,
                          background: active ? 'var(--accent-strong)' : 'var(--accent)',
                          opacity: active ? 1 : 0.55,
                        }}
                      />
                    )
                  })}
                </div>
              </div>
            )}
          </section>
        )}

        {previewEnabled && (
          <section
            className="mb-6"
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              padding: '16px 20px',
            }}
          >
            <h3 className="text-sm font-medium mb-3" style={{ color: 'var(--text)' }}>
              Match Preview
            </h3>

            {matchPreviewQuery.isLoading && (
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Loading matches…
              </p>
            )}

            {matchPreviewQuery.isError && (
              <p className="text-xs" style={{ color: 'var(--danger)' }}>
                Failed to load match preview
              </p>
            )}

            {matchPreviewQuery.isSuccess && !hasMatches && (
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                No matches found
              </p>
            )}

            {matchPreviewQuery.isSuccess && hasMatches && (
              <div style={{ overflowX: 'auto' }}>
                <table className="w-full text-xs border-collapse">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)' }}>
                      <th className="text-left py-1 pr-4 font-medium" style={{ color: 'var(--text-muted)' }}>
                        Filename
                      </th>
                      <th className="text-left py-1 pr-4 font-medium" style={{ color: 'var(--text-muted)' }}>
                        Matched Timestamp
                      </th>
                      <th className="text-left py-1 pr-4 font-medium" style={{ color: 'var(--text-muted)' }}>
                        Interpolation
                      </th>
                      <th className="text-left py-1 font-medium" style={{ color: 'var(--text-muted)' }}>
                        &Delta;t (sec){' '}
                        <InfoHint text="Δt: the time gap between the adjusted frame timestamp and the nearest raw flight-log entry. Smaller is a tighter match." />
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {matches.map((row) => (
                      <tr key={row.image_id} style={{ borderBottom: '1px solid var(--border)' }}>
                        <td className="py-1 pr-4" style={{ color: 'var(--text)' }}>
                          {row.filename}
                        </td>
                        <td className="py-1 pr-4" style={{ color: 'var(--text)' }}>
                          {row.matched_timestamp !== null ? row.matched_timestamp.toFixed(3) : '—'}
                        </td>
                        <td className="py-1 pr-4" style={{ color: 'var(--text)' }}>
                          {row.interpolated ? `${Math.round(row.interpolation_ratio * 100)}%` : 'edge'}
                        </td>
                        <td className="py-1" style={{ color: 'var(--text)' }}>
                          {row.delta_s !== null ? row.delta_s.toFixed(2) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            size="md"
            disabled={!hasMatches || applySync.isPending}
            onClick={() => {
              if (selectedSessionId !== null) {
                applySync.mutate({ sessionId: selectedSessionId, offsetS, toleranceS })
              }
            }}
          >
            {applySync.isPending ? 'Applying…' : 'Apply Sync'}
          </Button>
          {!hasMatches && previewEnabled && !matchPreviewQuery.isLoading && (
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Upload a flight log to enable sync
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
