export type ImportProgressStatus = 'pending' | 'running' | 'done' | 'error'

// Polling policy for the session-import progress query. Regression guard for walkthrough
// finding F5: keep polling (1000 ms) until the import reports done or error — including
// while status is still undefined right after the import starts.
export function importProgressRefetchInterval(
  status: ImportProgressStatus | undefined
): number | false {
  return status === 'done' || status === 'error' ? false : 1000
}
