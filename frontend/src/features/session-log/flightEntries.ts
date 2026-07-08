// Pure helpers for the battery/flight entries section (session field records).

export interface FlightEntryPayload {
  battery_id: string
  start_pct: number | null
  end_pct: number | null
  duration_s: number | null
  notes: string | null
}

export interface FlightEntryFormValues {
  batteryId: string
  startPct: string
  endPct: string
  durationMin: string
  notes: string
}

export type ParseResult =
  | { ok: true; payload: FlightEntryPayload }
  | { ok: false; error: string }

/** Format seconds as a compact duration, e.g. 750 -> "12m 30s". */
export function formatDurationS(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  const total = Math.round(seconds)
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  if (minutes === 0) return `${rest}s`
  return rest === 0 ? `${minutes}m` : `${minutes}m ${rest}s`
}

function parseOptionalNumber(raw: string, label: string): number | null | string {
  const trimmed = raw.trim()
  if (trimmed === '') return null
  const value = Number(trimmed)
  if (!Number.isFinite(value)) return `${label} must be a number`
  return value
}

/** Validate the add-entry form and build the API payload (duration entered in minutes). */
export function parseFlightEntryForm(values: FlightEntryFormValues): ParseResult {
  const batteryId = values.batteryId.trim()
  if (!batteryId) return { ok: false, error: 'Battery ID is required' }

  const pcts: Record<'start_pct' | 'end_pct', number | null> = {
    start_pct: null,
    end_pct: null,
  }
  for (const [key, raw, label] of [
    ['start_pct', values.startPct, 'Start %'],
    ['end_pct', values.endPct, 'End %'],
  ] as const) {
    const parsed = parseOptionalNumber(raw, label)
    if (typeof parsed === 'string') return { ok: false, error: parsed }
    if (parsed !== null && (parsed < 0 || parsed > 100)) {
      return { ok: false, error: `${label} must be between 0 and 100` }
    }
    pcts[key] = parsed
  }

  const durationMin = parseOptionalNumber(values.durationMin, 'Duration')
  if (typeof durationMin === 'string') return { ok: false, error: durationMin }
  if (durationMin !== null && durationMin < 0) {
    return { ok: false, error: 'Duration must be positive' }
  }

  const notes = values.notes.trim()
  return {
    ok: true,
    payload: {
      battery_id: batteryId,
      start_pct: pcts.start_pct,
      end_pct: pcts.end_pct,
      duration_s: durationMin === null ? null : durationMin * 60,
      notes: notes === '' ? null : notes,
    },
  }
}
