// Regression guard for walkthrough finding F6 ("Invalid Date" in the Session Log):
// null and unparseable timestamps render as an em dash, never "Invalid Date".
export function formatLogTimestamp(timestamp: string | null): string {
  if (!timestamp) return '—'
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString()
}
