import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useToast } from './useToast'

describe('useToast', () => {
  beforeEach(() => {
    useToast.setState({ toasts: [] })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('preserves crypto.randomUUID when it is available', () => {
    const randomUUID = vi.fn(() => 'native-uuid')
    vi.stubGlobal('crypto', { randomUUID })

    useToast.getState().addToast('Saved')

    expect(randomUUID).toHaveBeenCalledOnce()
    expect(useToast.getState().toasts[0]?.id).toBe('native-uuid')
  })

  it('creates unique toasts when crypto.randomUUID is unavailable', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00.000Z'))
    vi.stubGlobal('crypto', {})
    vi.spyOn(Math, 'random').mockReturnValue(0)

    expect(() => {
      useToast.getState().addToast('First')
      useToast.getState().addToast('Second')
    }).not.toThrow()

    const [first, second] = useToast.getState().toasts
    expect(first).toMatchObject({ message: 'First', type: 'info' })
    expect(second).toMatchObject({ message: 'Second', type: 'info' })
    expect(first?.id).toMatch(/^toast-/)
    expect(second?.id).toMatch(/^toast-/)
    expect(first?.id).not.toBe(second?.id)
  })
})
