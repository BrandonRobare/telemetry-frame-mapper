import { useQuery } from '@tanstack/react-query'
import type { Session } from '../../types/api'
import { get } from '../../shared/api/client'

export function useSessions(projectId: number | null) {
  const endpoint = projectId !== null ? `/projects/${projectId}/sessions` : '/sessions'
  return useQuery<Session[]>({
    queryKey: ['sessions', projectId],
    queryFn: () => get<Session[]>(endpoint),
    staleTime: 30_000,
  })
}
