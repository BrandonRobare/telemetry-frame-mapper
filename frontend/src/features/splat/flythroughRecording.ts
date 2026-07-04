export interface FlythroughRecordingRefs {
  rafRef: { current: number | null }
  recorderRef: { current: MediaRecorder | null }
}

export function cleanupFlythroughRecording(
  refs: FlythroughRecordingRefs,
  cancelAnimationFrameFn: (handle: number) => void = window.cancelAnimationFrame,
) {
  if (refs.rafRef.current !== null) {
    cancelAnimationFrameFn(refs.rafRef.current)
    refs.rafRef.current = null
  }

  const recorder = refs.recorderRef.current
  if (recorder && recorder.state !== 'inactive') {
    recorder.stop()
  }
  refs.recorderRef.current = null
}
