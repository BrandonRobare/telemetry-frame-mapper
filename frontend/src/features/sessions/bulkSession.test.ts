import { describe, expect, it } from 'vitest'
import { buildBulkRequest, canDelete, summarizeBulkResults } from './bulkSession'

describe('bulk session helpers', () => {
  it('builds only the fields required by the selected operation', () => {
    expect(buildBulkRequest('assign_project', [1, 2], { projectId: 7 })).toEqual({
      session_ids: [1, 2],
      operation: 'assign_project',
      project_id: 7,
    })
    expect(buildBulkRequest('delete', [4], { confirm: 'DELETE' })).toEqual({
      session_ids: [4],
      operation: 'delete',
      confirm: 'DELETE',
    })
  })

  it('requires the explicit delete value and summarizes partial outcomes', () => {
    expect(canDelete('delete', 2)).toBe(false)
    expect(canDelete('DELETE', 0)).toBe(false)
    expect(canDelete('DELETE', 2)).toBe(true)
    expect(summarizeBulkResults({
      operation: 'archive',
      outcomes: [
        { session_id: 1, ok: true, error: null, bundle_path: '/tmp/a.zip' },
        { session_id: 2, ok: false, error: 'disk full', bundle_path: null },
      ],
    })).toBe('1 completed, 1 failed')
  })
})
