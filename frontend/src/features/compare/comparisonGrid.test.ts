import { describe, expect, it } from 'vitest'
import { comparisonGridJobs } from './comparisonGrid'
import type { Job } from '../../types/api'

const jobs = [
  { id: 1, session_id: 10 },
  { id: 2, session_id: 20 },
  { id: 3, session_id: 30 },
] as Job[]

describe('comparisonGridJobs', () => {
  it('keeps selected reconstructions in slot order without duplicate panels', () => {
    expect(comparisonGridJobs(jobs, [1, 2, 1, 3]).map((job) => job.id)).toEqual([1, 2, 3])
  })

  it('ignores empty and unavailable slots', () => {
    expect(comparisonGridJobs(jobs, [null, 99, 2]).map((job) => job.id)).toEqual([2])
  })
})
