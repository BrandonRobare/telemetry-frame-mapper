export function formatRemainingDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds))

  if (seconds < 60) return `~${seconds}s remaining`

  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `~${minutes} min remaining`

  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  if (remainingMinutes === 0) return `~${hours}h remaining`
  return `~${hours}h ${remainingMinutes}m remaining`
}

export function formatEta(
  startedAt: string | null | undefined,
  progressPct: number | null | undefined,
  nowMs = Date.now()
): string | null {
  if (!startedAt || progressPct == null || !Number.isFinite(progressPct)) return null
  if (progressPct < 1 || progressPct >= 100) return null

  const startMs = new Date(startedAt).getTime()
  if (!Number.isFinite(startMs)) return null

  const elapsedSeconds = (nowMs - startMs) / 1000
  if (!Number.isFinite(elapsedSeconds) || elapsedSeconds <= 0) return null

  const remainingSeconds = (elapsedSeconds / progressPct) * (100 - progressPct)
  if (!Number.isFinite(remainingSeconds) || remainingSeconds < 1) return null

  return formatRemainingDuration(remainingSeconds)
}
