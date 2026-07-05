import { useQuery } from '@tanstack/react-query'
import type { QuickReport } from '../../../types/api'
import { get } from '../../../shared/api/client'

export function useQuickReport(id: number | null) {
  return useQuery<QuickReport>({
    queryKey: ['quick-report', id],
    queryFn: () => get<QuickReport>(`/sessions/${id}/quick-report`),
    enabled: id !== null,
    staleTime: 30_000,
  })
}