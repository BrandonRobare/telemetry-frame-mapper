import type { Job } from '../../types/api'

// Mirrors the ACTIVE status list used by usePipelineStatus / OverviewTab —
// jobs still moving through the reconstruction pipeline.
const ACTIVE_STATUSES = new Set<Job['status']>(['pending', 'running_colmap', 'running_gsplat'])

/** All in-flight jobs across every session, newest first. */
export function selectRunningJobs(jobs: Job[]): Job[] {
  return jobs
    .filter((j) => ACTIVE_STATUSES.has(j.status))
    .sort((a, b) => b.id - a.id)
}

/** Jobs belonging to one session, newest first. */
export function selectJobsForSession(jobs: Job[], sessionId: number | null): Job[] {
  if (sessionId === null) return []
  return jobs
    .filter((j) => j.session_id === sessionId)
    .sort((a, b) => b.id - a.id)
}
