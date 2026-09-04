import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiUrl, del, get } from '../../shared/api/client'
import ConfirmDialog from '../../shared/components/ConfirmDialog'
import { useToast } from '../../shared/hooks/useToast'
import type { Defect } from '../../types/api'
import { formatCategoryLabel, severityColorVar } from './defects'


/** Names the specific row a delete button acts on. */
function defectLabel(defect: Defect): string {
  return `${formatCategoryLabel(defect.category)} defect${defect.note ? `: ${defect.note}` : ''}`
}

function useDefects(sessionId: number) {
  return useQuery<Defect[]>({
    queryKey: ['defects', sessionId],
    queryFn: () => get<Defect[]>(`/sessions/${sessionId}/defects`),
  })
}

function thumbUrl(thumbPath: string | null): string | null {
  if (!thumbPath) return null
  return apiUrl(`/${thumbPath.replace(/\\/g, '/')}`)
}

export default function DefectsSection({ sessionId }: { sessionId: number }) {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const { data: defects = [] } = useDefects(sessionId)
  const [defectToDelete, setDefectToDelete] = useState<Defect | null>(null)

  const deleteDefect = useMutation({
    mutationFn: (defectId: number) => del(`/sessions/${sessionId}/defects/${defectId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['defects', sessionId] }),
    onError: (err: Error) => addToast(err.message || 'Delete failed', 'error'),
    onSettled: () => setDefectToDelete(null),
  })

  return (
    <section style={{ padding: '16px 24px 0' }}>
      <div
        className="text-xs uppercase tracking-wide"
        style={{ color: 'var(--text-muted)', marginBottom: 8 }}
      >
        Defects ({defects.length})
      </div>

      {defects.length === 0 && (
        <div className="text-xs" style={{ color: 'var(--text-faint)', marginBottom: 10 }}>
          No defects flagged yet. Flag one from a photo in the Review tab.
        </div>
      )}

      {/* Scrolls in its own box: the 24px target floor (#606) keeps the action
            column from shrinking, and the app shell is overflow-hidden, so at 320px
            an unwrapped table is clipped rather than reachable. */}
      {defects.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table
            style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, color: 'var(--text)' }}
          >
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Category', 'Severity', 'Note', 'Photos', ''].map((h, i) => (
                  <th
                    key={i}
                    className="text-left text-xs font-medium"
                    style={{ padding: '6px 12px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {defects.map((defect) => (
                <tr key={defect.id} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)' }}>
                    {formatCategoryLabel(defect.category)}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    {defect.severity ? (
                      <span style={{ color: severityColorVar(defect.severity), fontWeight: 600 }}>
                        {defect.severity}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-faint)' }}>—</span>
                    )}
                  </td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-muted)', maxWidth: 260 }}>
                    {defect.note ?? '—'}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {defect.images.map((img) => {
                        const url = thumbUrl(img.thumb_path)
                        return (
                          <span
                            key={img.id}
                            title={
                              img.latitude != null && img.longitude != null
                                ? `${img.filename} (${img.latitude.toFixed(5)}, ${img.longitude.toFixed(5)})`
                                : img.filename
                            }
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              width: 24,
                              height: 24,
                              borderRadius: 3,
                              overflow: 'hidden',
                              background: 'var(--surface-2)',
                              border: '1px solid var(--border)',
                              fontSize: 9,
                              color: 'var(--text-muted)',
                            }}
                          >
                            {url ? (
                              <img
                                src={url}
                                alt={img.filename}
                                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                              />
                            ) : (
                              img.filename.slice(0, 2).toUpperCase()
                            )}
                          </span>
                        )
                      })}
                    </div>
                  </td>
                  <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                    <button
                      onClick={() => setDefectToDelete(defect)}
                      aria-label={`Delete ${defectLabel(defect)}`}
                      title={`Delete ${defectLabel(defect)}`}
                      className="text-xs cursor-pointer"
                      style={{
                        background: 'transparent',
                        border: '1px solid var(--border-strong)',
                        color: 'var(--text-muted)',
                        padding: '2px 8px',
                      }}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={defectToDelete !== null}
        title="Delete defect?"
        description={<>Delete <strong>{defectToDelete && defectLabel(defectToDelete)}</strong>? This cannot be undone.</>}
        confirmLabel="Delete defect"
        danger
        loading={deleteDefect.isPending}
        onCancel={() => setDefectToDelete(null)}
        onConfirm={() => { if (defectToDelete) deleteDefect.mutate(defectToDelete.id) }}
      />
    </section>
  )
}
