import { useQuery } from '@tanstack/react-query'
import type { Session } from '../../types/api'
import { get } from '../../shared/api/client'

export function useSessions() {
  return useQuery<Session[]>({
    queryKey: ['sessions'],
    queryFn: () => get<Session[]>('/sessions'),
    staleTime: 30_000,
  })
}
