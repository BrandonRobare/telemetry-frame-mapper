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
export function formatCategoryLabel(category: DefectCategory): string {
  const known = CATEGORY_LABELS[category]
  if (known) return known
  return String(category).replace(/_/g, ' ')
}

const SEVERITY_COLOR_VAR: Record<DefectSeverity, string> = {
  low: 'var(--text-muted)',
  medium: 'var(--warning)',
  high: 'var(--danger)',
}

/** CSS color variable for a severity badge; a neutral fallback covers null/unset severity. */
export function severityColorVar(severity: DefectSeverity | null): string {
  if (severity == null) return 'var(--text-faint)'
  return SEVERITY_COLOR_VAR[severity] ?? 'var(--text-faint)'
}
