import { useQuery } from '@tanstack/react-query'
import { Session } from '../../../../types/api'
import { get } from '../../../../shared/api/client'

export function useSession(id: number | null) {
  return useQuery<Session>({
    queryKey: ['session', id],
    queryFn: () => get<Session>(`/sessions/${id}`),
    enabled: id !== null,
    staleTime: 30_000,
  })
}
