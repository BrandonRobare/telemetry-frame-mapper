// The quick-report `warnings` list mixes GPS-lock heuristic warnings (#384)
// in with blur/exposure/timestamp/coverage warnings. On the phone-sized
// quick-check view, space is tight, so GPS-lock warnings — the ones most
// likely to mean "this flight is unusable" — are surfaced first.

export function isGpsWarning(warning: string): boolean {
  return /gps/i.test(warning)
}

/** Stable-sorts GPS warnings ahead of the rest, then truncates to maxCount. */
export function prioritizeWarnings(warnings: string[], maxCount: number): string[] {
  const gps = warnings.filter(isGpsWarning)
  const rest = warnings.filter((w) => !isGpsWarning(w))
  return [...gps, ...rest].slice(0, maxCount)
}
