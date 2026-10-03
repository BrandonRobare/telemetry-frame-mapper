import type { SessionProgress } from '../../types/api'

export type ImportProgressStatus = SessionProgress['status']

// Polling policy for the session-import progress query: keep polling (1000 ms) until the
// import reports a terminal status — done, error, or unknown — including while status is
// still undefined right after the import starts. 'unknown' is terminal because the server
// keeps import progress in memory: after an API restart it can no longer report on an
// interrupted import (#507), so polling would otherwise spin forever. This logic has
// regressed before; it is pinned by a unit test.
export function importProgressRefetchInterval(
  status: ImportProgressStatus | undefined
): number | false {
  return status === 'done' || status === 'error' || status === 'unknown' ? false : 1000
}
