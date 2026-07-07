import { useQuery } from '@tanstack/react-query'
import type { Project } from '../../types/api'
import { get } from '../../shared/api/client'

export function useProjects() {
  return useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: () => get<Project[]>('/projects'),
    staleTime: 30_000,
  })
}