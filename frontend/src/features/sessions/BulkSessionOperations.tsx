import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { post } from '../../shared/api/client'
import { useMapStore } from '../../shared/stores/mapStore'
import type { BulkSessionOperation, BulkSessionResponse, Session } from '../../types/api'
import { buildBulkRequest, canDelete, summarizeBulkResults } from './bulkSession'
import { parseTagInput } from './sessionTags'
import { useProjects } from './useProjects'

interface Props {
  sessions: Session[]
}

const controlStyle: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--text)',
  fontFamily: 'inherit',
  fontSize: 11,
  padding: '3px 6px',
}

export default function BulkSessionOperations({ sessions }: Props) {
  const qc = useQueryClient()
  const { data: projects } = useProjects()
  const { selectedSessionId, setSession } = useMapStore()
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [projectId, setProjectId] = useState('')
  const [tagInput, setTagInput] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [result, setResult] = useState<BulkSessionResponse | null>(null)
  const visibleIds = sessions.map((session) => session.id)
  const selectedVisibleIds = selectedIds.filter((id) => visibleIds.includes(id))

  const mutation = useMutation({
    mutationFn: (body: ReturnType<typeof buildBulkRequest>) =>
      post<BulkSessionResponse>('/sessions/bulk', body),
    onSuccess: (data) => {
      setResult(data)
      if (data.operation === 'delete' && selectedVisibleIds.includes(selectedSessionId ?? -1)) {
        setSession(null)
      }
      setSelectedIds((ids) => ids.filter((id) => !data.outcomes.some(
        (outcome) => outcome.session_id === id && outcome.ok,
      )))
      qc.invalidateQueries({ queryKey: ['sessions'] })
      qc.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  function toggle(sessionId: number) {
    setSelectedIds((ids) => ids.includes(sessionId)
      ? ids.filter((id) => id !== sessionId)
      : [...ids, sessionId])
  }

  function selectAll() {
    setSelectedIds(selectedVisibleIds.length === visibleIds.length ? [] : visibleIds)
  }

  function run(
    operation: BulkSessionOperation,
    options: { projectId?: number; tags?: string[]; confirm?: string } = {},
  ) {
    if (selectedVisibleIds.length === 0) return
    mutation.mutate(buildBulkRequest(operation, selectedVisibleIds, options))
  }

  const tags = parseTagInput(tagInput)
  const actionDisabled = mutation.isPending || selectedVisibleIds.length === 0

  return (
    <details className="relative">
      <summary
        className="cursor-pointer select-none"
        style={{ ...controlStyle, display: 'block', listStyle: 'none', cursor: 'pointer' }}
      >
        Bulk{selectedVisibleIds.length ? ` (${selectedVisibleIds.length})` : ''}
      </summary>
      <div
        className="absolute"
        style={{
          top: 32,
          right: 0,
          zIndex: 50,
          width: 310,
          padding: 8,
          background: 'var(--surface)',
          border: '1px solid var(--border-strong)',
          boxShadow: 'var(--shadow-2)',
        }}
      >
        <div className="flex justify-between items-center" style={{ fontSize: 11, marginBottom: 6 }}>
          <strong>Selected sessions</strong>
          <button onClick={selectAll} disabled={mutation.isPending} style={controlStyle}>
            {selectedVisibleIds.length === visibleIds.length ? 'Clear' : 'All'}
          </button>
        </div>
        <div style={{ maxHeight: 130, overflowY: 'auto', borderBottom: '1px solid var(--border)', paddingBottom: 6 }}>
          {sessions.map((session) => (
            <label key={session.id} className="flex items-center gap-1.5" style={{ fontSize: 11, padding: '2px 0' }}>
              <input
                type="checkbox"
                checked={selectedVisibleIds.includes(session.id)}
                disabled={mutation.isPending}
                onChange={() => toggle(session.id)}
              />
              <span className="truncate">{session.name}</span>
            </label>
          ))}
        </div>

        <div className="flex gap-1" style={{ marginTop: 7 }}>
          <select
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
            aria-label="Assign selected sessions to project"
            style={{ ...controlStyle, flex: 1, minWidth: 0 }}
          >
            <option value="">Assign project…</option>
            {projects?.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
          <button
            onClick={() => run('assign_project', { projectId: Number(projectId) })}
            disabled={actionDisabled || !projectId}
            style={controlStyle}
          >
            Assign
          </button>
        </div>

        <div className="flex gap-1" style={{ marginTop: 5 }}>
          <input
            value={tagInput}
            onChange={(event) => setTagInput(event.target.value)}
            placeholder="Tags, comma-separated"
            aria-label="Bulk session tags"
            style={{ ...controlStyle, flex: 1, minWidth: 0 }}
          />
          <button onClick={() => run('add_tags', { tags })} disabled={actionDisabled || !tags.length} style={controlStyle}>Add</button>
          <button
            onClick={() => run('replace_tags', { tags })}
            disabled={actionDisabled}
            title={tags.length ? 'Replace tags' : 'Clear all tags'}
            style={controlStyle}
          >
            Replace
          </button>
        </div>

        <div className="flex gap-1" style={{ marginTop: 5 }}>
          <button onClick={() => run('archive')} disabled={actionDisabled} style={controlStyle}>Archive</button>
          <input
            value={deleteConfirm}
            onChange={(event) => setDeleteConfirm(event.target.value)}
            placeholder="Type DELETE"
            aria-label="Confirm bulk delete"
            style={{ ...controlStyle, flex: 1, minWidth: 0 }}
          />
          <button
            onClick={() => run('delete', { confirm: deleteConfirm })}
            disabled={mutation.isPending || !canDelete(deleteConfirm, selectedVisibleIds.length)}
            style={{ ...controlStyle, color: 'var(--danger)' }}
          >
            Delete
          </button>
        </div>

        <div style={{ minHeight: 17, marginTop: 6, fontSize: 10, color: 'var(--text-muted)' }}>
          {mutation.isPending && 'Applying…'}
          {mutation.isError && <span style={{ color: 'var(--danger)' }}>Bulk operation failed</span>}
          {result && !mutation.isPending && <span>{summarizeBulkResults(result)}</span>}
        </div>
        {result?.outcomes.filter((outcome) => !outcome.ok).map((outcome) => (
          <div key={outcome.session_id} style={{ fontSize: 10, color: 'var(--danger)' }}>
            #{outcome.session_id}: {outcome.error}
          </div>
        ))}
      </div>
    </details>
  )
}
