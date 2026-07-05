export function formatCoveragePct(coveragePct: number | null | undefined): string {
  return coveragePct === null || coveragePct === undefined ? 'N/A' : `${coveragePct.toFixed(0)}%`
}