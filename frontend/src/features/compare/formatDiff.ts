import type { ComparisonCell, ComparisonDiff } from '../../types/api'

export function visibleComparisonCells(
  diff: ComparisonDiff | null | undefined,
  showNew: boolean,
  showRemoved: boolean,
): ComparisonCell[] {
  if (!diff) return []
  return [
    ...(showNew ? diff.new : []),
    ...(showRemoved ? diff.removed : []),
  ]
}

export function formatComparisonSummary(diff: ComparisonDiff | null | undefined): string {
  if (!diff) return 'No diff loaded'
  const newCount = diff.summary.new_count
  const removedCount = diff.summary.removed_count
  return `${newCount} new · ${removedCount} removed`
}

export function normalizeCellsForOverlay(cells: ComparisonCell[]) {
  if (cells.length === 0) return []
  const xs = cells.map((cell) => cell.x)
  const ys = cells.map((cell) => cell.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const rangeX = maxX - minX || 1
  const rangeY = maxY - minY || 1
  return cells.map((cell) => ({
    ...cell,
    overlayX: ((cell.x - minX) / rangeX) * 92 + 4,
    overlayY: 96 - ((cell.y - minY) / rangeY) * 92,
  }))
}
