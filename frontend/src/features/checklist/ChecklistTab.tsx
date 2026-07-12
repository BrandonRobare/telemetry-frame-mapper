import { useState } from 'react'
import TabHeader from '../../shared/components/TabHeader'
import { Button } from '../../shared/components/Button'
import { useChecklistStore } from './checklistStore'
import { computeProgress, groupItems, type ChecklistGroup, type ChecklistItem } from './checklist'

const GROUP_LABELS: Record<ChecklistGroup, string> = {
  'pre-flight': 'Pre-flight',
  'post-flight': 'Post-flight',
}

const inputStyle: React.CSSProperties = {
  flex: 1,
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  color: 'var(--text)',
  fontFamily: 'inherit',
  fontSize: 12,
  padding: '5px 8px',
}

function ChecklistGroupSection({ group, items }: { group: ChecklistGroup; items: ChecklistItem[] }) {
  const toggle = useChecklistStore((s) => s.toggle)
  const add = useChecklistStore((s) => s.add)
  const remove = useChecklistStore((s) => s.remove)
  const [draft, setDraft] = useState('')
  const progress = computeProgress(items)

  function submitDraft() {
    if (!draft.trim()) return
    add(draft, group)
    setDraft('')
  }

  return (
    <section style={{ marginBottom: 28 }}>
      <div className="flex items-center justify-between" style={{ marginBottom: 10 }}>
        <h2
          className="text-sm font-semibold"
          style={{ color: 'var(--text)', margin: 0, fontFamily: 'var(--font-display)' }}
        >
          {GROUP_LABELS[group]}
        </h2>
        <span className="text-xs" style={{ color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
          {progress.completed}/{progress.total}
        </span>
      </div>

      <div
        aria-hidden="true"
        style={{ height: 3, background: 'var(--surface-2)', marginBottom: 14, overflow: 'hidden' }}
      >
        <div
          style={{
            height: '100%',
            width: `${progress.pct}%`,
            background: 'var(--accent-strong)',
            transition: 'width 200ms ease',
          }}
        />
      </div>

      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
        {items.length === 0 && (
          <li className="text-xs" style={{ color: 'var(--text-faint)', padding: '6px 4px' }}>
            No items — add one below.
          </li>
        )}
        {items.map((item) => (
          <li key={item.id} className="flex items-center gap-2" style={{ padding: '6px 4px' }}>
            <label className="flex items-center gap-2 flex-1" style={{ cursor: 'pointer', minWidth: 0 }}>
              <input
                type="checkbox"
                checked={item.checked}
                onChange={() => toggle(item.id)}
                style={{ accentColor: 'var(--accent)', width: 14, height: 14, flexShrink: 0 }}
              />
              <span
                className="text-sm"
                style={{
                  color: item.checked ? 'var(--text-muted)' : 'var(--text)',
                  textDecoration: item.checked ? 'line-through' : 'none',
                }}
              >
                {item.label}
              </span>
            </label>
            {item.custom && (
              <button
                onClick={() => remove(item.id)}
                title="Remove item"
                aria-label={`Remove ${item.label}`}
                className="text-xs cursor-pointer border-none bg-transparent"
                style={{ color: 'var(--text-faint)', padding: '2px 6px', flexShrink: 0 }}
              >
                ✕
              </button>
            )}
          </li>
        ))}
      </ul>

      <div className="flex items-center gap-2" style={{ marginTop: 10 }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submitDraft()
          }}
          placeholder="Add item…"
          aria-label={`Add ${GROUP_LABELS[group].toLowerCase()} item`}
          style={inputStyle}
        />
        <Button variant="ghost" size="sm" onClick={submitDraft} disabled={!draft.trim()}>
          Add
        </Button>
      </div>
    </section>
  )
}

export default function ChecklistTab() {
  const items = useChecklistStore((s) => s.items)
  const reset = useChecklistStore((s) => s.reset)
  const grouped = groupItems(items)
  const overall = computeProgress(items)

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <TabHeader
        title="Field Checklist"
        description="Pre-flight and post-flight reminders for the operator. Saved on this device only."
        right={
          <Button variant="ghost" size="sm" onClick={reset} disabled={overall.completed === 0}>
            Reset checks
          </Button>
        }
      />
      <div className="flex-1 overflow-auto" style={{ padding: 24 }}>
        <div style={{ maxWidth: 560 }}>
          <ChecklistGroupSection group="pre-flight" items={grouped['pre-flight']} />
          <ChecklistGroupSection group="post-flight" items={grouped['post-flight']} />
        </div>
      </div>
    </div>
  )
}
