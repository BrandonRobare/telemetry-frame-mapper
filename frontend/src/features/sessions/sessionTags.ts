import type { Session } from '../../types/api'

/** Mirror of the backend cap (backend/routers/sessions.py MAX_TAG_LENGTH). */
export const MAX_TAG_LENGTH = 40

/**
 * Parse a comma-separated tag input string into clean tags:
 * trimmed, empties dropped, de-duplicated, each capped at MAX_TAG_LENGTH.
 */
export function parseTagInput(input: string): string[] {
  const out: string[] = []
  for (const raw of input.split(',')) {
    const tag = raw.trim().slice(0, MAX_TAG_LENGTH)
    if (tag && !out.includes(tag)) out.push(tag)
  }
  return out
}

/** Unique tags across sessions, sorted alphabetically — for the filter dropdown. */
export function collectTags(sessions: Session[]): string[] {
  const set = new Set<string>()
  for (const s of sessions) for (const t of s.tags ?? []) set.add(t)
  return [...set].sort((a, b) => a.localeCompare(b))
}

/** Client-side tag filter; null tag means "show all". */
export function filterSessionsByTag(sessions: Session[], tag: string | null): Session[] {
  if (tag === null) return sessions
  return sessions.filter((s) => (s.tags ?? []).includes(tag))
}
