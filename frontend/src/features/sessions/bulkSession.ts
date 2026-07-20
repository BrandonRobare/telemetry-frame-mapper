import type { BulkSessionOperation, BulkSessionResponse } from '../../types/api'

export function buildBulkRequest(
  operation: BulkSessionOperation,
  sessionIds: number[],
  options: { projectId?: number; tags?: string[]; confirm?: string } = {},
) {
  return {
    session_ids: sessionIds,
    operation,
    ...(options.projectId !== undefined ? { project_id: options.projectId } : {}),
    ...(options.tags !== undefined ? { tags: options.tags } : {}),
    ...(options.confirm !== undefined ? { confirm: options.confirm } : {}),
  }
}

export function summarizeBulkResults(result: BulkSessionResponse): string {
  const completed = result.outcomes.filter((outcome) => outcome.ok).length
  const failed = result.outcomes.length - completed
  return failed ? `${completed} completed, ${failed} failed` : `${completed} completed`
}

export function canDelete(confirm: string, selectedCount: number): boolean {
  return selectedCount > 0 && confirm === 'DELETE'
}
