import { useQuery } from '@tanstack/react-query'
import { get } from './client'

export type SessionProgressStatus = 'pending' | 'running' | 'done' | 'error' | 'unknown'

export interface SessionProgress {
  processed: number
  total: number
  status: SessionProgressStatus
  error?: string
}

const LIVE_STATUSES = new Set<SessionProgressStatus>(['pending', 'running'])

export function isLiveImportStatus(status: SessionProgressStatus | undefined): boolean {
  return status !== undefined && LIVE_STATUSES.has(status)
}

/**
 * Poll interval for /sessions/{id}/progress when watching an arbitrary selected
 * session (not necessarily one this browser tab just started importing). Only
 * keeps polling while the status is actively 'pending' or 'running' — unlike the
 * import-modal's own progress poll (see importProgress.ts), 'unknown' and the
 * pre-response 'undefined' state stop polling here so that selecting a session
 * with no in-flight import doesn't poll forever (#361).
 */
export function sessionProgressRefetchInterval(
  status: SessionProgressStatus | undefined
): number | false {
  return isLiveImportStatus(status) ? 1500 : false
}

/** Tracks import progress for the given session so callers (e.g. the map view)
 * can tell whether footprints are still being written and should be polled live. */
export function useSessionProgress(sessionId: number | null) {
  return useQuery<SessionProgress>({
    queryKey: ['session-progress', sessionId],
    queryFn: () => get<SessionProgress>(`/sessions/${sessionId}/progress`),
    enabled: sessionId !== null,
    refetchInterval: (query) => sessionProgressRefetchInterval(query.state.data?.status),
  })
}
