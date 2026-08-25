import type { Job } from '../../types/api'
import { isLiveReconstructionStatus } from '../../shared/api/reconstructionStatusEvents'

/** All in-flight jobs across every session, newest first. */
export function selectRunningJobs(jobs: Job[]): Job[] {
  return jobs
    .filter((j) => isLiveReconstructionStatus(j.status))
    .sort((a, b) => b.id - a.id)
}

/** Jobs belonging to one session, newest first. */
export function selectJobsForSession(jobs: Job[], sessionId: number | null): Job[] {
  if (sessionId === null) return []
  return jobs
    .filter((j) => j.session_id === sessionId)
    .sort((a, b) => b.id - a.id)
}
