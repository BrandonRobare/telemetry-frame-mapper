import { describe, expect, it } from 'vitest'
import type { Job } from '../../../types/api'
import { latestCompletedReconstructionId, parseSlopeBounds } from './useSlopeOverlay'

function job(id: number, sessionId: number): Job {
  return {
    id,
    type: 'reconstruction',
    session_id: sessionId,
    source_session_ids: null,
    status: 'complete',
    preset: 'quick',
    progress_pct: 100,
    step: 'Complete',
    frames_used: 10,
    started_at: null,
    completed_at: null,
    error_msg: null,
  }
}

describe('slope overlay helpers', () => {
  it('uses the newest completed reconstruction for the current session', () => {
    expect(latestCompletedReconstructionId([job(9, 2), job(8, 1)], 2)).toBe(9)
    expect(latestCompletedReconstructionId([job(9, 2)], 1)).toBeNull()
  })

  it('accepts only ordered geographic bounds from the slope endpoint', () => {
    expect(parseSlopeBounds('[[40,-80],[41,-79]]')).toEqual([[40, -80], [41, -79]])
    expect(() => parseSlopeBounds('[[41,-80],[40,-79]]')).toThrow('invalid geographic bounds')
    expect(() => parseSlopeBounds(null)).toThrow('did not include geographic bounds')
  })
})
