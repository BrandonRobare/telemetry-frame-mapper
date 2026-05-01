import { useQuery } from '@tanstack/react-query'
import type { CoverageResult } from '../../../types/api'
import { get } from '../../../shared/api/client'

export function useCoverageResult(sessionId: number | null) {
  return useQuery<CoverageResult | null>({
    queryKey: ['coverage', sessionId],
    queryFn: () => get<CoverageResult | null>(`/coverage/results?session_id=${sessionId}`),
    enabled: sessionId !== null,
    staleTime: 30_000,
  })
}
