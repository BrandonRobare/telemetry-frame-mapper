import type { Job } from '../../types/api'

/**
 * Pick the reconstruction the Splat Viewer should render.
 *
 * The clicked id only wins while it is still a completed reconstruction of the
 * selected session; otherwise the session's newest-listed completed job (or
 * nothing) takes over. Deriving it this way means a stale selection can never
 * survive a session switch and leave the canvas streaming the previous
 * session's model (#656).
 */
export function resolveActiveJobId(
  selectedJobId: number | null,
  jobs: Job[],
  selectedSessionId: number | null,
): number | null {
  const completed = jobs.filter(
    (j) => j.status === 'complete' && j.session_id === selectedSessionId,
  )
  return completed.find((j) => j.id === selectedJobId)?.id ?? completed[0]?.id ?? null
}
