import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useProjects } from './useProjects'
import { useMapStore } from '../../shared/stores/mapStore'
import { Skeleton } from '../../shared/components/Skeleton'
import ConfirmDialog from '../../shared/components/ConfirmDialog'
import { del, post } from '../../shared/api/client'
import type { Project } from '../../types/api'

/** Sentinel option value — real ids are numbers. */
const NEW_PROJECT = '__new__'

const SELECT_STYLE: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--text)',
  fontSize: 12,
  fontFamily: 'inherit',
  padding: '3px 8px',
  cursor: 'pointer',
  maxWidth: 200,
  height: 28,
}

const INPUT_STYLE: React.CSSProperties = {
  ...SELECT_STYLE,
  cursor: 'text',
  width: 150,
}

export default function ProjectPicker() {
  const { data: projects, isLoading } = useProjects()
  const { selectedProjectId, setProject, setSession } = useMapStore()
  const prevProjectsLen = useRef(0)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  // When projects load for the first time and nothing is selected, pick the most recent.
  useEffect(() => {
    if (!projects || projects.length === 0) return
    const isFirstLoad = prevProjectsLen.current === 0
    prevProjectsLen.current = projects.length
    if (isFirstLoad && selectedProjectId === null) {
      setProject(projects[0].id)
    }
  }, [projects, selectedProjectId, setProject])

  useEffect(() => {
    if (creating) inputRef.current?.focus()
  }, [creating])

  const createProject = useMutation({
    mutationFn: (projectName: string) => post<Project>('/projects/', { name: projectName }),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setProject(project.id)
      setSession(null)
      setCreating(false)
      setName('')
      setError(null)
    },
    // The API returns 409 on a duplicate name; surface it rather than failing silently.
    onError: (err: Error) => setError(err.message || 'Could not create project'),
  })

  const deleteProject = useMutation({
    mutationFn: (project: Project) => del(`/projects/${project.id}`),
    onSuccess: (_, deleted) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      setProject(projects?.find((project) => project.id !== deleted.id)?.id ?? null)
      setSession(null)
      setProjectToDelete(null)
    },
    onError: (err: Error) => setError(err.message || 'Could not delete project'),
  })

  const submit = () => {
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Name is required')
      return
    }
    createProject.mutate(trimmed)
  }

  const cancel = () => {
    setCreating(false)
    setName('')
    setError(null)
  }

  const handleChange = (value: string) => {
    if (value === NEW_PROJECT) {
      setCreating(true)
      return
    }
    setProject(parseInt(value, 10))
    // Clear session selection when switching projects to avoid stale state.
    setSession(null)
  }

  if (isLoading) {
    return (
      <div style={{ padding: '0 8px' }}>
        <Skeleton width={150} height={20} radius="var(--radius-sm)" />
      </div>
    )
  }

  if (creating) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 8px' }}>
        <input
          ref={inputRef}
          value={name}
          onChange={(e) => { setName(e.target.value); setError(null) }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit()
            if (e.key === 'Escape') cancel()
          }}
          placeholder="Project name"
          aria-label="New project name"
          style={INPUT_STYLE}
          disabled={createProject.isPending}
        />
        <button
          onClick={submit}
          disabled={createProject.isPending}
          className="text-xs cursor-pointer border-none bg-transparent"
          style={{ color: 'var(--accent-strong)', fontFamily: 'inherit' }}
        >
          {createProject.isPending ? 'Creating…' : 'Create'}
        </button>
        <button
          onClick={cancel}
          className="text-xs cursor-pointer border-none bg-transparent"
          style={{ color: 'var(--text-muted)', fontFamily: 'inherit' }}
        >
          Cancel
        </button>
        {error && (
          <span className="text-xs" style={{ color: 'var(--danger, #b3261e)' }} role="alert">
            {error}
          </span>
        )}
      </div>
    )
  }

  // No projects yet — a bare button reads better than a one-option select.
  if (!projects || projects.length === 0) {
    return (
      <button
        onClick={() => setCreating(true)}
        className="text-xs cursor-pointer border-none bg-transparent"
        style={{ color: 'var(--accent-strong)', padding: '0 8px', fontFamily: 'inherit' }}
      >
        + New Project
      </button>
    )
  }

  return (
    <>
      <div className="flex items-center gap-1" style={{ padding: '0 8px' }}>
        <select
          value={selectedProjectId ?? ''}
          onChange={(e) => handleChange(e.target.value)}
          style={SELECT_STYLE}
          title="Select project"
        >
          {projects.map((p) => {
            const date = p.created_at
              ? new Date(p.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
              : null
            return (
              <option key={p.id} value={p.id}>
                {p.name}{date ? ` [${date}]` : ''}
              </option>
            )
          })}
          {/* Without this the create affordance disappeared as soon as one project existed. */}
          <option value={NEW_PROJECT}>+ New project…</option>
        </select>
        <button
          onClick={() => setProjectToDelete(projects.find((project) => project.id === selectedProjectId) ?? null)}
          aria-label="Delete selected project"
          title="Delete selected project"
          disabled={selectedProjectId === null}
          className="text-xs cursor-pointer border-none bg-transparent"
          style={{ color: 'var(--danger)', fontFamily: 'inherit' }}
        >
          Delete
        </button>
      </div>
      <ConfirmDialog
        open={projectToDelete !== null}
        title="Delete project?"
        description={<>Delete <strong>{projectToDelete?.name}</strong>, all its sessions, and their on-disk thumbnails, reconstruction outputs, and exports. Running reconstruction jobs will be cancelled. This cannot be undone.</>}
        confirmLabel="Delete project"
        danger
        loading={deleteProject.isPending}
        onCancel={() => setProjectToDelete(null)}
        onConfirm={() => { if (projectToDelete) deleteProject.mutate(projectToDelete) }}
      />
    </>
  )
}
