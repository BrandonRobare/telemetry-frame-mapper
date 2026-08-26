// @vitest-environment jsdom
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { ConfirmDialog } from './ConfirmDialog'

afterEach(() => {
  cleanup()
})

function renderDialog(props: Partial<React.ComponentProps<typeof ConfirmDialog>> = {}) {
  const onConfirm = vi.fn()
  const onCancel = vi.fn()
  render(
    <ConfirmDialog
      open
      title="Delete file?"
      description="This cannot be undone."
      confirmLabel="Delete"
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...props}
    />,
  )
  return { onConfirm, onCancel }
}

describe('ConfirmDialog', () => {
  it('moves focus into the dialog when it opens', () => {
    renderDialog()
    const dialog = screen.getByRole('alertdialog')
    expect(dialog.contains(document.activeElement)).toBe(true)
  })

  it('traps Tab focus within the dialog, wrapping at both ends', () => {
    renderDialog()
    const cancelButton = screen.getByRole('button', { name: 'Cancel' })
    const confirmButton = screen.getByRole('button', { name: 'Delete' })

    expect(document.activeElement).toBe(cancelButton)

    // Shift+Tab from the first control wraps around to the last.
    fireEvent.keyDown(cancelButton, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(confirmButton)

    // Tab from the last control wraps back to the first.
    fireEvent.keyDown(confirmButton, { key: 'Tab' })
    expect(document.activeElement).toBe(cancelButton)
  })

  it('closes on Escape by calling onCancel (and not onConfirm)', () => {
    const { onCancel, onConfirm } = renderDialog()
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('ignores Escape while a confirmation is pending', () => {
    const { onCancel } = renderDialog({ loading: true })
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' })
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('restores focus to the triggering control when it closes', () => {
    function Harness() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button onClick={() => setOpen(true)}>Open dialog</button>
          <ConfirmDialog
            open={open}
            title="Delete file?"
            description="This cannot be undone."
            confirmLabel="Delete"
            onConfirm={() => setOpen(false)}
            onCancel={() => setOpen(false)}
          />
        </>
      )
    }
    render(<Harness />)
    const trigger = screen.getByRole('button', { name: 'Open dialog' })
    trigger.focus()
    expect(document.activeElement).toBe(trigger)

    fireEvent.click(trigger)
    expect(document.activeElement).not.toBe(trigger)

    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' })
    expect(document.activeElement).toBe(trigger)
  })

  it('gives two simultaneously open dialogs distinct label/description ids', () => {
    render(
      <>
        <ConfirmDialog open title="First" description="d1" confirmLabel="Ok" onConfirm={vi.fn()} onCancel={vi.fn()} />
        <ConfirmDialog open title="Second" description="d2" confirmLabel="Ok" onConfirm={vi.fn()} onCancel={vi.fn()} />
      </>,
    )
    const [firstDialog, secondDialog] = screen.getAllByRole('alertdialog')
    const firstLabelledBy = firstDialog.getAttribute('aria-labelledby')
    const secondLabelledBy = secondDialog.getAttribute('aria-labelledby')

    expect(firstLabelledBy).toBeTruthy()
    expect(secondLabelledBy).toBeTruthy()
    expect(firstLabelledBy).not.toBe(secondLabelledBy)
    expect(document.getElementById(firstLabelledBy!)?.textContent).toBe('First')
    expect(document.getElementById(secondLabelledBy!)?.textContent).toBe('Second')
  })
})
