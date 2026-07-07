import { useEffect, useRef } from 'react'
import { useProjects } from './useProjects'
import { useMapStore } from '../../shared/stores/mapStore'
import { Skeleton } from '../../shared/components/Skeleton'

interface ProjectPickerProps {
  /** Called when the user clicks "+ New Project" */
  onCreateProject?: () => void
}

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

export default function ProjectPicker({ onCreateProject }: ProjectPickerProps) {
  const { data: projects, isLoading } = useProjects()
  const { selectedProjectId, setProject, setSession } = useMapStore()
  const prevProjectsLen = useRef(0)

  // When projects load for the first time and nothing is selected, pick the most recent.
  useEffect(() => {
    if (!projects || projects.length === 0) return
    // If we already had projects loaded (non-zero) and now have more,
    // we still want to auto-select on first load only.
    const isFirstLoad = prevProjectsLen.current === 0
    prevProjectsLen.current = projects.length
    if (isFirstLoad && selectedProjectId === null) {
      setProject(projects[0].id)
    }
  }, [projects, selectedProjectId, setProject])

  const handleChange = (projectId: number) => {
    setProject(projectId)
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

  if (!projects || projects.length === 0) {
    return (
      <button
        onClick={onCreateProject}
        className="text-xs cursor-pointer border-none bg-transparent"
        style={{ color: 'var(--accent-strong)', padding: '0 8px', fontFamily: 'inherit' }}
      >
        + New Project
      </button>
    )
  }

  return (
    <select
      value={selectedProjectId ?? ''}
      onChange={(e) => handleChange(parseInt(e.target.value, 10))}
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
    </select>
  )
}