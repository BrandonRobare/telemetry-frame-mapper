import { useEffect, useId, useRef } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { Button } from './Button'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: ReactNode
  confirmLabel: string
  cancelLabel?: string
  danger?: boolean
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = 'Cancel',
  danger = false,
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const titleId = useId()
  const descriptionId = useId()
  const dialogRef = useRef<HTMLElement>(null)
  const previouslyFocusedRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return

    const dialog = dialogRef.current
    previouslyFocusedRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null

    const focusable = dialog?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
    ;(focusable && focusable.length > 0 ? focusable[0] : dialog)?.focus()

    // Safety net: if focus ever ends up outside the dialog while it's open
    // (e.g. the focused button becomes disabled mid-confirm), pull it back in.
    const handleFocusIn = (event: FocusEvent) => {
      if (dialog && !dialog.contains(event.target as Node)) dialog.focus()
    }
    document.addEventListener('focusin', handleFocusIn)

    return () => {
      document.removeEventListener('focusin', handleFocusIn)
      const previous = previouslyFocusedRef.current
      if (previous && document.contains(previous)) previous.focus()
    }
  }, [open])

  if (!open) return null

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      if (!loading) onCancel()
      return
    }
    if (event.key !== 'Tab') return

    const dialog = dialogRef.current
    const focusable = dialog ? Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)) : []
    if (focusable.length === 0) {
      event.preventDefault()
      return
    }

    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div
      role="presentation"
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(29, 23, 18, 0.46)' }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !loading) onCancel()
      }}
    >
      <section
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className="w-full max-w-sm p-5"
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border-strong)',
          borderRadius: 'var(--edge)',
          boxShadow: 'var(--shadow-3)',
          color: 'var(--text)',
        }}
      >
        <h2 id={titleId} className="font-semibold" style={{ fontSize: 'var(--text-lg)', lineHeight: 'var(--leading-tight)', margin: 0 }}>
          {title}
        </h2>
        <div id={descriptionId} className="mt-2" style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-normal)' }}>
          {description}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button type="button" variant={danger ? 'danger' : 'primary'} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </div>
      </section>
    </div>
  )
}

export default ConfirmDialog
