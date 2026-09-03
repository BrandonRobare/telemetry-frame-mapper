import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post } from '../../shared/api/client'
import ConfirmDialog from '../../shared/components/ConfirmDialog'
import { useToast } from '../../shared/hooks/useToast'
import type { FlightEntry } from '../../types/api'
import { formatDurationS, parseFlightEntryForm } from './flightEntries'

const EMPTY_FORM = { batteryId: '', startPct: '', endPct: '', durationMin: '', notes: '' }

const inputStyle: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  color: 'var(--text)',
  fontFamily: 'inherit',
  fontSize: 12,
  padding: '5px 8px',
  minWidth: 0,
}

/** Names the specific row a delete button acts on. */
function entryLabel(entry: FlightEntry): string {
  return entry.battery_id
    ? `battery ${entry.battery_id}`
    : `flight recorded ${new Date(entry.created_at).toLocaleString()}`
}

function useFlightEntries(sessionId: number) {
  return useQuery<FlightEntry[]>({
    queryKey: ['flight-entries', sessionId],
    queryFn: () => get<FlightEntry[]>(`/sessions/${sessionId}/flight-entries`),
  })
}

export default function FlightEntriesSection({ sessionId }: { sessionId: number }) {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const { data: entries = [] } = useFlightEntries(sessionId)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formError, setFormError] = useState<string | null>(null)
  const [entryToDelete, setEntryToDelete] = useState<FlightEntry | null>(null)

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['flight-entries', sessionId] })

  const createEntry = useMutation({
    mutationFn: (payload: unknown) =>
      post<FlightEntry>(`/sessions/${sessionId}/flight-entries`, payload),
    onSuccess: () => {
      setForm(EMPTY_FORM)
      setFormError(null)
      invalidate()
    },
    onError: (err: Error) => setFormError(err.message),
  })

  const deleteEntry = useMutation({
    mutationFn: (entryId: number) => del(`/sessions/${sessionId}/flight-entries/${entryId}`),
    onSuccess: invalidate,
    onError: (err: Error) => addToast(err.message || 'Delete failed', 'error'),
    onSettled: () => setEntryToDelete(null),
  })

  function submit() {
    const result = parseFlightEntryForm(form)
    if (!result.ok) {
      setFormError(result.error)
      return
    }
    createEntry.mutate(result.payload)
  }

  const field = (key: keyof typeof EMPTY_FORM, placeholder: string, width: number) => (
    <input
      value={form[key]}
      onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
      onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
      placeholder={placeholder}
      aria-label={placeholder}
      style={{ ...inputStyle, width }}
    />
  )

  return (
    <section style={{ padding: '16px 24px 0' }}>
      <div
        className="text-xs uppercase tracking-wide"
        style={{ color: 'var(--text-muted)', marginBottom: 8 }}
      >
        Battery / flight records
      </div>

      {/* Add form */}
      <div className="flex flex-wrap items-center gap-2" style={{ marginBottom: 10 }}>
        {field('batteryId', 'Battery ID', 110)}
        {field('startPct', 'Start %', 70)}
        {field('endPct', 'End %', 70)}
        {field('durationMin', 'Duration (min)', 100)}
        {field('notes', 'Note (optional)', 220)}
        <button
          onClick={submit}
          disabled={createEntry.isPending}
          className="text-xs cursor-pointer border-none transition-all duration-150 active:scale-[0.98]"
          style={{
            padding: '6px 14px',
            background: 'var(--accent-strong)',
            color: 'var(--on-accent)',
            fontFamily: 'inherit',
            opacity: createEntry.isPending ? 0.7 : 1,
          }}
        >
          {createEntry.isPending ? 'Adding…' : 'Add flight'}
        </button>
      </div>
      {formError && (
        <div className="text-xs" style={{ color: 'var(--danger, #f85149)', marginBottom: 8 }}>
          {formError}
        </div>
      )}
      <div className="text-xs" style={{ color: 'var(--text-faint)', marginBottom: 10 }}>
        Duration is filled from the flight log automatically when left blank.
      </div>

      {/* Entries list */}
      {entries.length > 0 && (
        <table
          style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, color: 'var(--text)' }}
        >
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Battery', 'Start', 'End', 'Duration', 'Note', ''].map((h, i) => (
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
            {entries.map((entry) => (
              <tr key={entry.id} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)' }}>
                  {entry.battery_id ?? '—'}
                </td>
                <td style={{ padding: '8px 12px', color: 'var(--text-muted)' }}>
                  {entry.start_pct != null ? `${entry.start_pct.toFixed(0)}%` : '—'}
                </td>
                <td style={{ padding: '8px 12px', color: 'var(--text-muted)' }}>
                  {entry.end_pct != null ? `${entry.end_pct.toFixed(0)}%` : '—'}
                </td>
                <td style={{ padding: '8px 12px', color: 'var(--text-muted)' }}>
                  {formatDurationS(entry.duration_s)}
                </td>
                <td style={{ padding: '8px 12px', color: 'var(--text-muted)' }}>
                  {entry.notes ?? '—'}
                </td>
                <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                  <button
                    onClick={() => setEntryToDelete(entry)}
                    aria-label={`Delete ${entryLabel(entry)}`}
                    title={`Delete ${entryLabel(entry)}`}
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
      )}

      <ConfirmDialog
        open={entryToDelete !== null}
        title="Delete flight entry?"
        description={<>Delete the entry for <strong>{entryToDelete && entryLabel(entryToDelete)}</strong>? This cannot be undone.</>}
        confirmLabel="Delete entry"
        danger
        loading={deleteEntry.isPending}
        onCancel={() => setEntryToDelete(null)}
        onConfirm={() => { if (entryToDelete) deleteEntry.mutate(entryToDelete.id) }}
      />
    </section>
  )
}
