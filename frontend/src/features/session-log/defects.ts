// Pure helpers for the defect-flagging feature (categories, severity, labels).
import type { DefectCategory, DefectSeverity } from '../../types/api'

export const CATEGORY_LABELS: Record<DefectCategory, string> = {
  crack: 'Crack',
  corrosion: 'Corrosion',
  vegetation: 'Vegetation',
  water_damage: 'Water damage',
  missing_material: 'Missing material',
  other: 'Other',
}

export const SEVERITY_LABELS: Record<DefectSeverity, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
}

/** Human-readable label for a defect category, tolerant of categories not yet in the map. */
export function formatCategoryLabel(category: string): string {
  const known = Object.entries(CATEGORY_LABELS).find(([key]) => key === category)?.[1]
  if (known) return known
  return String(category).replace(/_/g, ' ')
}

const SEVERITY_COLOR_VAR: Record<DefectSeverity, string> = {
  low: 'var(--text-muted)',
  medium: 'var(--warning)',
  high: 'var(--danger)',
}

/** CSS color variable for a severity badge; a neutral fallback covers null/unset severity. */
export function severityColorVar(severity: string | null): string {
  if (severity == null) return 'var(--text-faint)'
  return Object.entries(SEVERITY_COLOR_VAR).find(([key]) => key === severity)?.[1] ?? 'var(--text-faint)'
}
