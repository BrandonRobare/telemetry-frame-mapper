import type { Job } from '../../types/api'
import type { ToastType } from '../hooks/useToast'
import { isLiveReconstructionStatus } from '../api/reconstructionStatusEvents'

export type JobOutcome = 'succeeded' | 'failed' | 'cancelled'

export interface JobTransition {
  job: Job
  outcome: JobOutcome
}

export interface JobNotificationContent {
  title: string
  body: string
  toastType: ToastType
}

/** Snapshot job id → status, for diffing against the next poll/SSE update. */
export function nextStatusMap(jobs: readonly Job[]): Map<number, Job['status']> {
  return new Map(jobs.map((job) => [job.id, job.status]))
}

function outcomeFor(status: Job['status']): JobOutcome | null {
  if (status === 'complete') return 'succeeded'
  if (status === 'failed') return 'failed'
  if (status === 'cancelled') return 'cancelled'
  return null
}

/**
 * Diff the previous status snapshot against the current job list and return
 * jobs that transitioned from a live status (pending/running/cancelling) to a
 * terminal one. Jobs first seen already terminal never fire — this prevents a
 * notification storm on initial load or after a page refresh.
 */
export function detectJobTransitions(
  previous: ReadonlyMap<number, Job['status']>,
  jobs: readonly Job[]
): JobTransition[] {
  const transitions: JobTransition[] = []
  for (const job of jobs) {
    const before = previous.get(job.id)
    if (before === undefined || !isLiveReconstructionStatus(before)) continue
    const outcome = outcomeFor(job.status)
    if (outcome) transitions.push({ job, outcome })
  }
  return transitions
}

export function formatJobNotification(job: Job, outcome: JobOutcome): JobNotificationContent {
  const label = `Reconstruction #${job.id}`
  const context = `Session ${job.session_id} · ${job.preset} · ${job.frames_used} frames`
  if (outcome === 'succeeded') {
    return { title: `${label} complete`, body: context, toastType: 'success' }
  }
  if (outcome === 'failed') {
    const reason = job.error_msg?.trim()
    return {
      title: `${label} failed`,
      body: reason ? `${context} — ${reason}` : context,
      toastType: 'error',
    }
  }
  return { title: `${label} cancelled`, body: context, toastType: 'info' }
}
