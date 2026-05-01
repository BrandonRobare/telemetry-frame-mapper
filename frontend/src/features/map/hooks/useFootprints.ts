import { useQuery } from '@tanstack/react-query'
import { Footprint } from '../../../../types/api'
import { get } from '../../../../shared/api/client'

export function useFootprints(sessionId: number | null) {
  return useQuery<Footprint[]>({
    queryKey: ['footprints', sessionId],
    queryFn: () => get<Footprint[]>(`/images?session_id=${sessionId}&has_footprint=true`),
    enabled: sessionId !== null,
    staleTime: 30_000,
  })
}
