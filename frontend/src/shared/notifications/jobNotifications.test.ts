import { describe, expect, it } from 'vitest'
import {
  detectJobTransitions,
  formatJobNotification,
  nextStatusMap,
  shouldShowDesktopNotification,
} from './jobNotifications'
import type { Job } from '../../types/api'

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 1,
    type: 'reconstruction',
    session_id: 7,
    source_session_ids: null,
    status: 'running_colmap',
    preset: 'balanced',
    progress_pct: 50,
    step: 'Feature extraction',
    frames_used: 120,
    started_at: '2026-07-08T00:00:00Z',
    completed_at: null,
    error_msg: null,
    ...overrides,
  }
}

describe('nextStatusMap', () => {
  it('maps job id to current status', () => {
    const jobs = [makeJob({ id: 1, status: 'running_colmap' }), makeJob({ id: 2, status: 'complete' })]
    const map = nextStatusMap(jobs)
    expect(map.get(1)).toBe('running_colmap')
    expect(map.get(2)).toBe('complete')
    expect(map.size).toBe(2)
  })
})

describe('detectJobTransitions', () => {
  it('fires a succeeded transition when a live job completes', () => {
    const previous = new Map([[1, 'running_gsplat' as Job['status']]])
    const jobs = [makeJob({ id: 1, status: 'complete' })]
    const transitions = detectJobTransitions(previous, jobs)
    expect(transitions).toEqual([{ job: jobs[0], outcome: 'succeeded' }])
  })

  it('fires a failed transition when a live job fails', () => {
    const previous = new Map([[1, 'running_colmap' as Job['status']]])
    const jobs = [makeJob({ id: 1, status: 'failed', error_msg: 'COLMAP crashed' })]
    const transitions = detectJobTransitions(previous, jobs)
    expect(transitions).toEqual([{ job: jobs[0], outcome: 'failed' }])
  })

  it('fires a cancelled transition when a live job is cancelled', () => {
    const previous = new Map([[1, 'cancelling' as Job['status']]])
    const jobs = [makeJob({ id: 1, status: 'cancelled' })]
    const transitions = detectJobTransitions(previous, jobs)
    expect(transitions).toEqual([{ job: jobs[0], outcome: 'cancelled' }])
  })

  it('does not fire for progress updates within a still-running job', () => {
    const previous = new Map([[1, 'running_colmap' as Job['status']]])
    const jobs = [makeJob({ id: 1, status: 'running_gsplat', progress_pct: 80 })]
    expect(detectJobTransitions(previous, jobs)).toEqual([])
  })

  it('does not fire retroactively for a job seen for the first time already finished', () => {
    const previous = new Map<number, Job['status']>()
    const jobs = [makeJob({ id: 1, status: 'complete' })]
    expect(detectJobTransitions(previous, jobs)).toEqual([])
  })

  it('does not fire when a job was already terminal and stays terminal', () => {
    const previous = new Map([[1, 'complete' as Job['status']]])
    const jobs = [makeJob({ id: 1, status: 'complete' })]
    expect(detectJobTransitions(previous, jobs)).toEqual([])
  })

  it('handles multiple simultaneous transitions', () => {
    const previous = new Map([
      [1, 'running_colmap' as Job['status']],
      [2, 'running_gsplat' as Job['status']],
      [3, 'pending' as Job['status']],
    ])
    const jobs = [
      makeJob({ id: 1, status: 'complete' }),
      makeJob({ id: 2, status: 'failed' }),
      makeJob({ id: 3, status: 'running_colmap' }),
    ]
    const transitions = detectJobTransitions(previous, jobs)
    expect(transitions).toEqual([
      { job: jobs[0], outcome: 'succeeded' },
      { job: jobs[1], outcome: 'failed' },
    ])
  })
})

describe('formatJobNotification', () => {
  it('formats a succeeded job', () => {
    const job = makeJob({ id: 42, status: 'complete', session_id: 3, preset: 'high-quality' })
    const result = formatJobNotification(job, 'succeeded')
    expect(result.toastType).toBe('success')
    expect(result.title).toContain('42')
    expect(result.body).toContain('3')
  })

  it('formats a failed job including the error message', () => {
    const job = makeJob({ id: 42, status: 'failed', error_msg: 'Out of memory' })
    const result = formatJobNotification(job, 'failed')
    expect(result.toastType).toBe('error')
    expect(result.body).toContain('Out of memory')
  })

  it('formats a cancelled job', () => {
    const job = makeJob({ id: 42, status: 'cancelled' })
    const result = formatJobNotification(job, 'cancelled')
    expect(result.toastType).toBe('info')
    expect(result.title).toContain('cancelled')
  })
})

describe('shouldShowDesktopNotification', () => {
  it('shows only when the tab is hidden and permission is granted', () => {
    expect(shouldShowDesktopNotification(true, 'granted')).toBe(true)
  })

  it('does not show when the tab is focused', () => {
    expect(shouldShowDesktopNotification(false, 'granted')).toBe(false)
  })

  it('does not show without permission', () => {
    expect(shouldShowDesktopNotification(true, 'denied')).toBe(false)
    expect(shouldShowDesktopNotification(true, 'default')).toBe(false)
  })

  it('degrades silently when the Notification API is unavailable', () => {
    expect(shouldShowDesktopNotification(true, undefined)).toBe(false)
  })
})
