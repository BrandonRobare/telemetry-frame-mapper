// @vitest-environment jsdom
//
// WCAG 2.2 SC 2.5.8 (#606).
//
// Scope, stated plainly: jsdom performs no layout, so nothing here measures a
// real box. What it does check is the part of the contract that lives in
// TypeScript — the shared Button's inline floor, and the stepper that makes the
// exempt histogram reachable. The app-wide CSS floor in index.css cannot be
// asserted from here (Vitest returns CSS imports empty, and reading the file
// needs node types the app tsconfig deliberately excludes); that rule is
// verified in a browser instead, at 320/375/430/desktop.
import { useState } from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { Button } from '../../shared/components/Button'
import { OffsetStepper } from './GpsSyncTab'

afterEach(() => {
  cleanup()
})

const MIN_TARGET_PX = '24px'

describe('shared Button target-size floor', () => {
  it.each(['sm', 'md'] as const)('applies a 24x24 floor at size %s', (size) => {
    render(<Button size={size}>Go</Button>)
    const button = screen.getByRole('button', { name: 'Go' })
    expect(button.style.minHeight).toBe(MIN_TARGET_PX)
    expect(button.style.minWidth).toBe(MIN_TARGET_PX)
  })

  it('still lets a caller override the floor, which is why the CSS rule exists too', () => {
    // `style` spreads last in Button, so an inline padding/size from a caller
    // wins. That is exactly why the floor is also enforced app-wide in
    // index.css rather than only here.
    render(
      <Button size="sm" style={{ minHeight: 8 }}>
        Squashed
      </Button>,
    )
    expect(screen.getByRole('button', { name: 'Squashed' }).style.minHeight).toBe('8px')
  })
})

describe('OffsetStepper — the conformant path to the exempt histogram', () => {
  const offsets = [-2, -1, 0, 1, 2]

  function renderStepper(initial = 0) {
    function Harness() {
      const [value, setValue] = useState(initial)
      return <OffsetStepper offsets={offsets} value={value} onChange={setValue} />
    }
    return render(<Harness />)
  }

  it('exposes named controls rather than unlabelled glyphs', () => {
    renderStepper()
    expect(screen.getByRole('button', { name: 'Previous offset' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Next offset' })).toBeTruthy()
    expect(screen.getByRole('group', { name: /step through previewed offsets/i })).toBeTruthy()
  })

  it('steps onto adjacent previewed offsets', () => {
    renderStepper(0)
    fireEvent.click(screen.getByRole('button', { name: 'Next offset' }))
    expect(screen.getByText('1.0 s')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Previous offset' }))
    fireEvent.click(screen.getByRole('button', { name: 'Previous offset' }))
    expect(screen.getByText('-1.0 s')).toBeTruthy()
  })

  it('stops at both ends instead of stepping off the list', () => {
    renderStepper(-2)
    expect((screen.getByRole('button', { name: 'Previous offset' }) as HTMLButtonElement).disabled).toBe(
      true,
    )

    cleanup()
    renderStepper(2)
    expect((screen.getByRole('button', { name: 'Next offset' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('snaps an off-grid value onto the nearest previewed offset', () => {
    renderStepper(0.6)
    fireEvent.click(screen.getByRole('button', { name: 'Next offset' }))
    expect(screen.getByText('1.0 s')).toBeTruthy()
  })
})
