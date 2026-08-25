import { describe, expect, it } from 'vitest'
import { isLiveReconstructionStatus } from './reconstructionStatusEvents'

describe('isLiveReconstructionStatus', () => {
  it('returns true only for active reconstruction statuses', () => {
    expect(isLiveReconstructionStatus('pending')).toBe(true)
    expect(isLiveReconstructionStatus('running_colmap')).toBe(true)
    expect(isLiveReconstructionStatus('running_gsplat')).toBe(true)
    expect(isLiveReconstructionStatus('running_remote')).toBe(true)
    expect(isLiveReconstructionStatus('cancelling')).toBe(true)
    expect(isLiveReconstructionStatus('complete')).toBe(false)
    expect(isLiveReconstructionStatus('failed')).toBe(false)
    expect(isLiveReconstructionStatus('cancelled')).toBe(false)
  })
})
