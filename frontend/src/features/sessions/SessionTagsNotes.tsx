import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { patch } from '../../shared/api/client'
import type { Session } from '../../types/api'
import { parseTagInput } from './sessionTags'

interface Props {
  session: Session
}

/**
 * Field-organization metadata editor: tag chips + free-text operator notes.
 * Persists via PATCH /sessions/{id} (issue #369).
 *
 * Render with ``key={session.id}`` so the notes draft resets when the
 * active session changes.
 */
export default function SessionTagsNotes({ session }: Props) {
  const qc = useQueryClient()
  const [tagInput, setTagInput] = useState('')
  const [notesDraft, setNotesDraft] = useState(session.notes ?? '')

  const mutation = useMutation({
    mutationFn: (body: { tags?: string[]; notes?: string }) =>
      patch<Session>(`/sessions/${session.id}`, body),
    onSuccess: (data, variables) => {
      // Align the draft with what the server actually stored (trimming etc.).
      if (variables.notes !== undefined) setNotesDraft(data.notes ?? '')
      qc.invalidateQueries({ queryKey: ['session', session.id] })
      qc.invalidateQueries({ queryKey: ['sessions'] })
    },
  })

  const tags = session.tags ?? []

  function addTags() {
    const parsed = parseTagInput(tagInput)
    if (parsed.length === 0) return
    const merged = [...tags]
    for (const t of parsed) if (!merged.includes(t)) merged.push(t)
    mutation.mutate({ tags: merged })
    setTagInput('')
  }

  function removeTag(tag: string) {
    mutation.mutate({ tags: tags.filter((t) => t !== tag) })
  }

  function saveNotes() {
    if (notesDraft === (session.notes ?? '')) return
    mutation.mutate({ notes: notesDraft })
  }

  const notesDirty = notesDraft !== (session.notes ?? '')

  return (
    <div className="px-3 py-2" style={{ borderBottom: '1px solid var(--border)' }}>
      <div className="text-xs uppercase tracking-wide mb-2" style={{ color: 'var(--text-muted)' }}>
        Tags &amp; Notes
      </div>

      {/* tag chips */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-1.5">
          {tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1"
              style={{
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 999,
                padding: '1px 4px 1px 8px',
                fontSize: 11,
                color: 'var(--text)',
              }}
            >
              {tag}
              <button
                onClick={() => removeTag(tag)}
                disabled={mutation.isPending}
                aria-label={`Remove tag ${tag}`}
                title={`Remove tag ${tag}`}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'var(--text-muted)',
                  fontSize: 11,
                  padding: '0 2px',
                  fontFamily: 'inherit',
                }}
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}

      {/* tag input */}
      <div className="flex gap-1 mb-2">
        <input
          type="text"
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              addTags()
            }
          }}
          placeholder="Add tags (comma-separated)"
          aria-label="Add tags"
          className="flex-1 min-w-0"
          style={{
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text)',
            fontSize: 11,
            fontFamily: 'inherit',
            padding: '3px 6px',
          }}
        />
        <button
          onClick={addTags}
          disabled={mutation.isPending || parseTagInput(tagInput).length === 0}
          style={{
            background: 'var(--surface-2)',
            border: '1px solid var(--border-strong)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text)',
            fontSize: 11,
            fontFamily: 'inherit',
            padding: '3px 8px',
            cursor: 'pointer',
            opacity: parseTagInput(tagInput).length === 0 ? 0.5 : 1,
          }}
        >
          Add
        </button>
      </div>

      {/* operator notes */}
      <textarea
        value={notesDraft}
        onChange={(e) => setNotesDraft(e.target.value)}
        onBlur={saveNotes}
        placeholder="Operator notes — conditions, obstacles, follow-ups…"
        aria-label="Operator notes"
        rows={3}
        className="w-full"
        style={{
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--text)',
          fontSize: 11,
          fontFamily: 'inherit',
          padding: '4px 6px',
          resize: 'vertical',
        }}
      />
      <div className="flex justify-between items-center" style={{ minHeight: 16 }}>
        <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>
          {mutation.isPending ? 'Saving…' : notesDirty ? 'Unsaved — click away to save' : ''}
        </span>
        {mutation.isError && (
          <span style={{ fontSize: 10, color: 'var(--danger)' }}>Save failed</span>
        )}
      </div>
    </div>
  )
}
