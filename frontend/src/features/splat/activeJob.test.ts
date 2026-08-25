import { describe, expect, it } from 'vitest'
import { resolveActiveJobId } from './activeJob'
import type { Job } from '../../types/api'

/**
 * Switching sessions used to leave the viewer streaming the previous session's
 * reconstruction: `selectedJobId` was component state that nothing reset, so
 * the operator reviewed session B while looking at session A's site (#656).
 */
describe('resolveActiveJobId', () => {
  const job = (id: number, session_id: number, status: Job['status'] = 'complete'): Job => ({
    id,
    type: 'reconstruction',
    session_id,
    source_session_ids: null,
    status,
    preset: 'balanced',
    progress_pct: 100,
    step: 'done',
    frames_used: 120,
    started_at: null,
    completed_at: null,
    error_msg: null,
  })

  const sessionA = [job(12, 1), job(11, 1)]
  const sessionB = [job(31, 2), job(30, 2)]

  it('keeps the clicked reconstruction while its session stays selected', () => {
    expect(resolveActiveJobId(11, sessionA, 1)).toBe(11)
  })

  it('drops session A\'s selection once session B is selected', () => {
    expect(resolveActiveJobId(12, sessionB, 2)).toBe(31)
  })

  it('never returns a reconstruction from another session, even if the job list is stale', () => {
    expect(resolveActiveJobId(12, sessionA, 2)).toBeNull()
  })

  it('falls back to the first completed job when nothing is selected', () => {
    expect(resolveActiveJobId(null, sessionB, 2)).toBe(31)
  })

  it('ignores a selection that is not complete', () => {
    const jobs = [job(40, 3, 'running_gsplat'), job(41, 3)]
    expect(resolveActiveJobId(40, jobs, 3)).toBe(41)
  })

  it('returns null when the session has no completed reconstructions', () => {
    expect(resolveActiveJobId(12, [job(50, 4, 'failed')], 4)).toBeNull()
    expect(resolveActiveJobId(12, [], null)).toBeNull()
  })
})
