import { useState } from 'react'

interface InfoHintProps {
  /** Help text shown on hover/focus. */
  text: string
  /** Accessible label (defaults to "More info"). */
  label?: string
}

/* Small "?" affordance with a hover/focus tooltip — adds inline help for jargon
   (COLMAP, SIFT, LOD, reprojection error…) without cluttering the layout. */
export function InfoHint({ text, label = 'More info' }: InfoHintProps) {
  const [open, setOpen] = useState(false)
  return (
    <span style={{ position: 'relative', display: 'inline-flex', verticalAlign: 'middle' }}>
      <button
        type="button"
        aria-label={label}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="cursor-help"
        style={{
          // 24px hit target for touch / pointer accuracy; the visible mark
          // stays a compact 14px circle inside.
          width: 24,
          height: 24,
          padding: 0,
          border: 'none',
          background: 'transparent',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 14,
            height: 14,
            borderRadius: '50%',
            border: '1px solid var(--border-strong)',
            background: 'var(--surface-2)',
            color: 'var(--text-muted)',
            fontSize: 10,
            fontWeight: 600,
            lineHeight: 1,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: 'var(--font-display)',
          }}
        >
          ?
        </span>
      </button>
      {open && (
        <span
          role="tooltip"
          style={{
            position: 'absolute',
            bottom: 'calc(100% + 7px)',
            left: '50%',
            transform: 'translateX(-50%)',
            width: 'max-content',
            maxWidth: 240,
            background: 'var(--text)',
            color: 'var(--surface)',
            fontSize: 11.5,
            lineHeight: 1.45,
            padding: '7px 10px',
            borderRadius: 'var(--radius-sm)',
            boxShadow: 'var(--shadow-2)',
            zIndex: 60,
            pointerEvents: 'none',
            fontFamily: 'var(--font-sans)',
            fontWeight: 400,
            textTransform: 'none',
            letterSpacing: 'normal',
          }}
        >
          {text}
        </span>
      )}
    </span>
  )
}

export default InfoHint
