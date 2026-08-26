import { describe, expect, it } from 'vitest'
import type { Job } from '../../types/api'
import { selectJobsForSession, selectRunningJobs } from './jobsSummary'

function makeJob(overrides: Partial<Job>): Job {
  return {
    id: 1,
    type: 'reconstruction',
    session_id: 1,
    source_session_ids: null,
    status: 'pending',
    preset: 'quick',
    progress_pct: 0,
    step: '',
    frames_used: 0,
    started_at: null,
    completed_at: null,
    error_msg: null,
    ...overrides,
  }
}

describe('selectRunningJobs', () => {
  it('keeps only jobs in an active status', () => {
    const jobs = [
      makeJob({ id: 1, status: 'pending' }),
      makeJob({ id: 2, status: 'running_colmap' }),
      makeJob({ id: 3, status: 'running_gsplat' }),
      makeJob({ id: 4, status: 'complete' }),
      makeJob({ id: 5, status: 'failed' }),
      makeJob({ id: 6, status: 'cancelled' }),
      makeJob({ id: 7, status: 'running_remote' }),
      makeJob({ id: 8, status: 'cancelling' }),
    ]
    expect(selectRunningJobs(jobs).map((j) => j.id)).toEqual([8, 7, 3, 2, 1])
  })

  it('sorts running jobs newest-first by id', () => {
    const jobs = [
      makeJob({ id: 2, status: 'running_colmap' }),
      makeJob({ id: 5, status: 'pending' }),
      makeJob({ id: 3, status: 'running_gsplat' }),
    ]
    expect(selectRunningJobs(jobs).map((j) => j.id)).toEqual([5, 3, 2])
  })

  it('returns an empty array when nothing is running', () => {
    const jobs = [makeJob({ id: 1, status: 'complete' })]
    expect(selectRunningJobs(jobs)).toEqual([])
  })
})

describe('selectJobsForSession', () => {
  const jobs = [
    makeJob({ id: 1, session_id: 10, status: 'complete' }),
    makeJob({ id: 2, session_id: 20, status: 'running_colmap' }),
    makeJob({ id: 3, session_id: 10, status: 'failed' }),
  ]

  it('returns only jobs for the given session, newest first', () => {
    expect(selectJobsForSession(jobs, 10).map((j) => j.id)).toEqual([3, 1])
  })

  it('returns an empty array when sessionId is null', () => {
    expect(selectJobsForSession(jobs, null)).toEqual([])
  })

  it('returns an empty array when no jobs match the session', () => {
    expect(selectJobsForSession(jobs, 999)).toEqual([])
  })
})
