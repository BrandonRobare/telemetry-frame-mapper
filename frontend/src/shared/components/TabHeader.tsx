import React from 'react'
import { useMapStore } from '../stores/mapStore'

interface TabHeaderProps {
  /** Tab name. */
  title: string
  /** One line: what this tab is for. */
  description: string
  /** Optional "next step" link — routes to this tab id. */
  nextTab?: string
  nextLabel?: string
  /** Optional right-aligned slot (e.g. a primary action that belongs in the header). */
  right?: React.ReactNode
}

/* Consistent purpose header for every feature tab — teaches the mental model
   and the paradox of the active user (what does this screen do, what's next?). */
export function TabHeader({ title, description, nextTab, nextLabel, right }: TabHeaderProps) {
  const setRequestedTab = useMapStore((s) => s.setRequestedTab)
  return (
    <div
      className="shrink-0 flex items-center justify-between gap-4"
      style={{
        padding: '13px 20px',
        background: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 600,
            fontSize: 15,
            color: 'var(--text)',
            margin: 0,
            lineHeight: 1.2,
          }}
        >
          {title}
        </h1>
        <p style={{ fontSize: 12.5, color: 'var(--text-muted)', margin: '2px 0 0', lineHeight: 1.4 }}>
          {description}
        </p>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        {right}
        {nextTab && (
          <button
            onClick={() => setRequestedTab(nextTab)}
            className="cursor-pointer border-none bg-transparent"
            style={{ fontFamily: 'var(--font-display)', fontSize: 12.5, color: 'var(--accent-strong)', padding: 0, whiteSpace: 'nowrap' }}
          >
            {nextLabel ?? 'Next'} →
          </button>
        )}
      </div>
    </div>
  )
}

export default TabHeader
