import { useQuery } from '@tanstack/react-query'
import { useRef } from 'react'
import type { Footprint } from '../../../types/api'
import { get } from '../../../shared/api/client'

const LIVE_POLL_MS = 1500

/** Highest footprint id in the list, or 0 if empty — used as the since_id cursor
 * for the next incremental poll. */
export function latestFootprintId(footprints: Footprint[]): number {
  return footprints.reduce((max, fp) => Math.max(max, fp.id), 0)
}

/** Appends a newly-fetched page onto the accumulated footprint list. Returns the
 * original array reference when the page is empty so callers can skip re-renders. */
export function mergeFootprintPage(existing: Footprint[], page: Footprint[]): Footprint[] {
  if (page.length === 0) return existing
  return [...existing, ...page]
}

interface UseFootprintsOptions {
  /** Poll incrementally via the since_id cursor while true — used while a
   * session's import is still running so the map can render footprints
   * accumulating live instead of waiting for import to finish (#361). */
  live?: boolean
}

interface FootprintCursorState {
  sessionId: number | null
  footprints: Footprint[]
  sinceId: number
}

export function useFootprints(sessionId: number | null, options?: UseFootprintsOptions) {
  const live = options?.live ?? false
  // Cursor state is only ever read/written from inside queryFn (an async
  // callback invoked by react-query outside of render), never during render.
  const cursor = useRef<FootprintCursorState>({ sessionId: null, footprints: [], sinceId: 0 })

  return useQuery<Footprint[]>({
    queryKey: ['footprints', sessionId],
    queryFn: async () => {
      // A previous session's accumulated footprints must never leak into a
      // newly-selected session's incremental fetch.
      if (cursor.current.sessionId !== sessionId) {
        cursor.current = { sessionId, footprints: [], sinceId: 0 }
      }
      const params = new URLSearchParams({ session_id: String(sessionId) })
      if (live) params.set('since_id', String(cursor.current.sinceId))
      const page = await get<Footprint[]>(`/footprints?${params.toString()}`)
      const merged = live ? mergeFootprintPage(cursor.current.footprints, page) : page
      cursor.current = { sessionId, footprints: merged, sinceId: latestFootprintId(merged) }
      return merged
    },
    enabled: sessionId !== null,
    staleTime: live ? 0 : 30_000,
    refetchInterval: live ? LIVE_POLL_MS : false,
  })
}
