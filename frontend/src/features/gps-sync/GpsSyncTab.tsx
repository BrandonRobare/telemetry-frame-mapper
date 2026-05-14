import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useMapStore } from '../../shared/stores/mapStore'
import { useApplyFlightSync } from '../../shared/api/mutations'
import { useToast } from '../../shared/hooks/useToast'
import { Button } from '../../shared/components/Button'
import { get } from '../../shared/api/client'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

interface MatchPreviewRow {
  filename: string
  matched_timestamp: string | null
  delta_sec: number | null
}

export default function GpsSyncTab() {
  const { selectedSessionId } = useMapStore()
  const { addToast } = useToast()
  const applySync = useApplyFlightSync()

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSuccess, setUploadSuccess] = useState(false)
  // Toggle to trigger match preview refetch after upload
  const [previewEnabled, setPreviewEnabled] = useState(false)

  const matchPreviewQuery = useQuery({
    queryKey: ['match-preview', selectedSessionId],
    queryFn: () =>
      get<MatchPreviewRow[]>(`/flight-logs/match-preview?session_id=${selectedSessionId}`),
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
      const res = await fetch(
        `${BASE_URL}/flight-logs/upload?session_id=${selectedSessionId}`,
        { method: 'POST', body: formData }
      )
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `Upload failed (${res.status})`)
      }
      setUploadSuccess(true)
      setPreviewEnabled(true)
      matchPreviewQuery.refetch()
      addToast('Flight log uploaded', 'success')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Upload failed'
      setUploadError(msg)
      addToast(msg, 'error')
    } finally {
      setUploading(false)
      // Reset file input so the same file can be re-uploaded if needed
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  if (selectedSessionId === null) {
    return (
      <div
        className="flex-1 flex items-center justify-center"
        style={{ color: 'var(--text-muted)' }}
      >
        <p>Select a session first</p>
      </div>
    )
  }

  return (
    <div
      className="flex-1 overflow-y-auto"
      style={{ padding: '24px 32px', background: 'var(--bg)', color: 'var(--text)' }}
    >
      <h2 className="text-base font-semibold mb-6" style={{ color: 'var(--text)' }}>
        GPS Sync
      </h2>

      {/* Upload section */}
      <section
        className="rounded mb-6"
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
            <span className="text-xs" style={{ color: 'var(--accent)' }}>
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

      {/* Match preview table */}
      {previewEnabled && (
        <section
          className="rounded mb-6"
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
                    <th
                      className="text-left py-1 pr-4 font-medium"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      Filename
                    </th>
                    <th
                      className="text-left py-1 pr-4 font-medium"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      Matched Timestamp
                    </th>
                    <th
                      className="text-left py-1 font-medium"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      &Delta;t (sec)
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {matches.map((row) => (
                    <tr
                      key={row.filename}
                      style={{ borderBottom: '1px solid var(--border)' }}
                    >
                      <td className="py-1 pr-4" style={{ color: 'var(--text)' }}>
                        {row.filename}
                      </td>
                      <td className="py-1 pr-4" style={{ color: 'var(--text)' }}>
                        {row.matched_timestamp ?? '—'}
                      </td>
                      <td className="py-1" style={{ color: 'var(--text)' }}>
                        {row.delta_sec !== null ? row.delta_sec.toFixed(2) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* Apply Sync button */}
      <div className="flex items-center gap-3">
        <Button
          variant="primary"
          size="md"
          disabled={!hasMatches || applySync.isPending}
          onClick={() => {
            if (selectedSessionId !== null) {
              applySync.mutate(selectedSessionId)
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
  )
}
