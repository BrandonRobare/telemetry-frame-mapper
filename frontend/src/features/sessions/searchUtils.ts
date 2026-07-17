import type { SessionSearchSource } from '../../types/api'

export const SEARCH_SOURCES: Array<SessionSearchSource | ''> = ['', 'session', 'log', 'defect']

export const sourceLabel = (source: SessionSearchSource) => (
  source === 'session' ? 'Session' : source === 'log' ? 'Log' : 'Defect'
)

export function buildSessionSearchPath(query: string, source: SessionSearchSource | ''): string {
  const params = new URLSearchParams({ q: query })
  if (source) params.set('source', source)
  return `/sessions/search?${params}`
}
