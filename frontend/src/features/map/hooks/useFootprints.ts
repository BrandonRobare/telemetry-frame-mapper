import { useQuery } from '@tanstack/react-query'
import type { Footprint } from '../../../types/api'
import { get } from '../../../shared/api/client'

export function useFootprints(sessionId: number | null) {
  return useQuery<Footprint[]>({
    queryKey: ['footprints', sessionId],
    queryFn: () => get<Footprint[]>(`/footprints?session_id=${sessionId}`),
    enabled: sessionId !== null,
    staleTime: 30_000,
  })
}
