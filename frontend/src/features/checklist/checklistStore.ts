import { create } from 'zustand'
import {
  type ChecklistGroup,
  type ChecklistItem,
  addItem,
  createDefaultChecklist,
  removeItem,
  resetChecklist,
  toggleItem,
} from './checklist'

// ---------------------------------------------------------------------------
// GUI-only, device-local state — the field checklist has no server component
// (it's a lightweight operator reminder, not part of the session record) —
// persisted to localStorage, same pattern as settingsStore.
// ---------------------------------------------------------------------------

export const STORAGE_KEY = 'field-checklist'

interface ChecklistStore {
  items: ChecklistItem[]
  toggle: (id: string) => void
  add: (label: string, group: ChecklistGroup) => void
  remove: (id: string) => void
  reset: () => void
}

function loadItems(): ChecklistItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return createDefaultChecklist()
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) && parsed.length > 0 ? (parsed as ChecklistItem[]) : createDefaultChecklist()
  } catch {
    return createDefaultChecklist()
  }
}

function saveItems(items: ChecklistItem[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
  } catch {
    // Quota exceeded or private browsing — silently ignore
  }
}

function makeItemId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `item-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export const useChecklistStore = create<ChecklistStore>((set, get) => ({
  items: loadItems(),

  toggle: (id) => {
    const items = toggleItem(get().items, id)
    set({ items })
    saveItems(items)
  },
  add: (label, group) => {
    const items = addItem(get().items, makeItemId(), label, group)
    set({ items })
    saveItems(items)
  },
  remove: (id) => {
    const items = removeItem(get().items, id)
    set({ items })
    saveItems(items)
  },
  reset: () => {
    const items = resetChecklist(get().items)
    set({ items })
    saveItems(items)
  },
}))
