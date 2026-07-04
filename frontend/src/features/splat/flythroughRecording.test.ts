import { describe, expect, it, vi } from 'vitest'
import { cleanupFlythroughRecording, type FlythroughRecordingRefs } from './flythroughRecording'

describe('cleanupFlythroughRecording', () => {
  it('cancels a pending animation frame and stops active recorder', () => {
    const cancelAnimationFrame = vi.fn()
    const recorder = { state: 'recording', stop: vi.fn() } as unknown as MediaRecorder
    const refs: FlythroughRecordingRefs = {
      rafRef: { current: 123 },
      recorderRef: { current: recorder },
    }

    cleanupFlythroughRecording(refs, cancelAnimationFrame)

    expect(cancelAnimationFrame).toHaveBeenCalledWith(123)
    expect(refs.rafRef.current).toBeNull()
    expect(recorder.stop).toHaveBeenCalledOnce()
    expect(refs.recorderRef.current).toBeNull()
  })

  it('does not stop an inactive recorder', () => {
    const cancelAnimationFrame = vi.fn()
    const recorder = { state: 'inactive', stop: vi.fn() } as unknown as MediaRecorder
    const refs: FlythroughRecordingRefs = {
      rafRef: { current: null },
      recorderRef: { current: recorder },
    }

    cleanupFlythroughRecording(refs, cancelAnimationFrame)

    expect(cancelAnimationFrame).not.toHaveBeenCalled()
    expect(recorder.stop).not.toHaveBeenCalled()
    expect(refs.recorderRef.current).toBeNull()
  })
})
