import { describe, expect, it } from 'vitest'
import { isLiveImportStatus, sessionProgressRefetchInterval } from './useSessionProgress'

describe('isLiveImportStatus', () => {
  it('is true only while an import is actively pending or running', () => {
    expect(isLiveImportStatus('pending')).toBe(true)
    expect(isLiveImportStatus('running')).toBe(true)
    expect(isLiveImportStatus('done')).toBe(false)
    expect(isLiveImportStatus('error')).toBe(false)
    expect(isLiveImportStatus('unknown')).toBe(false)
    expect(isLiveImportStatus(undefined)).toBe(false)
  })
})

describe('sessionProgressRefetchInterval', () => {
  it('polls while pending or running', () => {
    expect(sessionProgressRefetchInterval('pending')).toBe(1500)
    expect(sessionProgressRefetchInterval('running')).toBe(1500)
  })

  it('stops for done, error, and unknown so unrelated sessions are not polled forever', () => {
    expect(sessionProgressRefetchInterval('done')).toBe(false)
    expect(sessionProgressRefetchInterval('error')).toBe(false)
    expect(sessionProgressRefetchInterval('unknown')).toBe(false)
  })

  it('does not poll before the first response (avoids a storm on unrelated sessions)', () => {
    expect(sessionProgressRefetchInterval(undefined)).toBe(false)
  })
})
