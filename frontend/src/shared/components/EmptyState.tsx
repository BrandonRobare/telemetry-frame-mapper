import React from 'react'
import Button from './Button'
import CornerTicks from './CornerTicks'

interface EmptyStateProps {
  /** Short heading, e.g. "Select a session". */
  title: string
  /** One or two lines explaining what this tab does / what's needed. */
  description: string
  actionLabel?: string
  onAction?: () => void
  /** Optional custom glyph; defaults to a stacked-layers mark. */
  icon?: React.ReactNode
}

function DefaultIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 3 3 7.5 12 12l9-4.5L12 3Z" fill="var(--accent-soft)" stroke="var(--accent)" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M3 12l9 4.5L21 12M3 16.5 12 21l9-4.5" stroke="var(--accent)" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

/* Standard empty / needs-session state: a helpful prompt instead of a bare
   "Select a session first" — says what the tab does and offers the next action. */
export function EmptyState({ title, description, actionLabel, onAction, icon }: EmptyStateProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center" style={{ padding: 32 }}>
      <div
        className="flex items-center justify-center relative"
        style={{
          width: 56,
          height: 56,
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          marginBottom: 18,
        }}
      >
        <CornerTicks size={7} />
        {icon ?? <DefaultIcon />}
      </div>
      <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 16, color: 'var(--text)', margin: 0 }}>
        {title}
      </h2>
      <p
        className="text-center"
        style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.55, margin: '6px 0 0', maxWidth: 360 }}
      >
        {description}
      </p>
      {actionLabel && onAction && (
        <div className="mt-5">
          <Button onClick={onAction}>{actionLabel}</Button>
        </div>
      )}
    </div>
  )
}

export default EmptyState
