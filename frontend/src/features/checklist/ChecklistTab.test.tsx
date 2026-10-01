// level: component; area: platform-ops
import { afterEach, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ChecklistTab from './ChecklistTab'
import { useChecklistStore } from './checklistStore'

const initialItems = useChecklistStore.getState().items
afterEach(() => { cleanup(); useChecklistStore.setState({ items: initialItems }) })

it('adds, checks, resets, and removes a custom pre-flight reminder', async () => {
  render(<ChecklistTab />)
  expect(screen.getByRole('heading', { name: 'Field Checklist' })).toBeTruthy()
  await userEvent.type(screen.getByLabelText('Add pre-flight item'), 'Inspect propellers{Enter}')
  const checkbox = screen.getByRole('checkbox', { name: 'Inspect propellers' })
  await userEvent.click(checkbox)
  expect((checkbox as HTMLInputElement).checked).toBe(true)
  await userEvent.click(screen.getByRole('button', { name: 'Reset checks' }))
  expect((checkbox as HTMLInputElement).checked).toBe(false)
  await userEvent.click(screen.getByRole('button', { name: 'Remove Inspect propellers' }))
  expect(screen.queryByRole('checkbox', { name: 'Inspect propellers' })).toBeNull()
})
