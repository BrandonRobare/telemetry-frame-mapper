import type { ReactNode } from 'react'
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
  if (!open) return null

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
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-description"
        className="w-full max-w-sm p-5"
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border-strong)',
          borderRadius: 'var(--edge)',
          boxShadow: 'var(--shadow-3)',
          color: 'var(--text)',
        }}
      >
        <h2 id="confirm-dialog-title" className="font-semibold" style={{ fontSize: 'var(--text-lg)', lineHeight: 'var(--leading-tight)', margin: 0 }}>
          {title}
        </h2>
        <div id="confirm-dialog-description" className="mt-2" style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-normal)' }}>
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
