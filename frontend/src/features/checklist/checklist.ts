// Pure helpers for the field checklist (pre-flight/post-flight operator reminders).
// State lives in checklistStore.ts (localStorage-backed); this module has no
// side effects, which keeps it easy to unit test in isolation.

export type ChecklistGroup = 'pre-flight' | 'post-flight'

export interface ChecklistItem {
  id: string
  label: string
  group: ChecklistGroup
  checked: boolean
  /** Operator-added item (can be removed) vs. a built-in default (cannot). */
  custom: boolean
}

interface DefaultItemSeed {
  id: string
  label: string
  group: ChecklistGroup
}

const DEFAULT_ITEM_SEEDS: DefaultItemSeed[] = [
  { id: 'preflight-batteries', label: 'Batteries charged', group: 'pre-flight' },
  { id: 'preflight-sd-card', label: 'SD card formatted / empty', group: 'pre-flight' },
  { id: 'preflight-propellers', label: 'Propellers inspected', group: 'pre-flight' },
  { id: 'preflight-firmware-rth', label: 'Firmware updated, RTH height set', group: 'pre-flight' },
  { id: 'preflight-gps-lock', label: 'GPS lock acquired', group: 'pre-flight' },
  { id: 'preflight-takeoff-altitude', label: 'Takeoff altitude recorded', group: 'pre-flight' },
  { id: 'postflight-video-srt', label: 'Video + SRT copied off aircraft', group: 'post-flight' },
  { id: 'postflight-frames', label: 'Frames extracted', group: 'post-flight' },
  { id: 'postflight-battery-state', label: 'Battery state noted', group: 'post-flight' },
]

/** Build the default checklist — all items unchecked, none custom. */
export function createDefaultChecklist(): ChecklistItem[] {
  return DEFAULT_ITEM_SEEDS.map((seed) => ({ ...seed, checked: false, custom: false }))
}

/** Flip the checked state of one item. No-op if the id isn't found. */
export function toggleItem(items: ChecklistItem[], id: string): ChecklistItem[] {
  return items.map((item) => (item.id === id ? { ...item, checked: !item.checked } : item))
}

/**
 * Append a new custom, unchecked item to the given group.
 * `id` is supplied by the caller so this stays pure.
 * Blank labels (after trimming) are ignored.
 */
export function addItem(
  items: ChecklistItem[],
  id: string,
  label: string,
  group: ChecklistGroup,
): ChecklistItem[] {
  const trimmed = label.trim()
  if (!trimmed) return items
  return [...items, { id, label: trimmed, group, checked: false, custom: true }]
}

/** Remove an item by id. No-op if the id isn't found. */
export function removeItem(items: ChecklistItem[], id: string): ChecklistItem[] {
  return items.filter((item) => item.id !== id)
}

/**
 * Uncheck every item ahead of the next flight, keeping the full item list
 * (including operator-added custom items) intact.
 */
export function resetChecklist(items: ChecklistItem[]): ChecklistItem[] {
  return items.map((item) => (item.checked ? { ...item, checked: false } : item))
}

export interface ChecklistProgress {
  total: number
  completed: number
  /** Percentage complete, rounded to the nearest whole number. 0 when total is 0. */
  pct: number
}

/** Completion stats, optionally scoped to a single group. */
export function computeProgress(items: ChecklistItem[], group?: ChecklistGroup): ChecklistProgress {
  const scoped = group ? items.filter((item) => item.group === group) : items
  const total = scoped.length
  const completed = scoped.filter((item) => item.checked).length
  const pct = total === 0 ? 0 : Math.round((completed / total) * 100)
  return { total, completed, pct }
}

/** Bucket items by group, preserving relative order within each bucket. */
export function groupItems(items: ChecklistItem[]): Record<ChecklistGroup, ChecklistItem[]> {
  return {
    'pre-flight': items.filter((item) => item.group === 'pre-flight'),
    'post-flight': items.filter((item) => item.group === 'post-flight'),
  }
}
