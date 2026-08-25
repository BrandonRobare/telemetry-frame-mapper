import { useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Job } from '../../../types/api'
import { apiUrl, get } from '../../../shared/api/client'

export type SlopeBounds = [[number, number], [number, number]]

export function parseSlopeBounds(value: string | null): SlopeBounds {
  if (!value) throw new Error('Slope overlay did not include geographic bounds')
  const bounds: unknown = JSON.parse(value)
  if (!Array.isArray(bounds) || bounds.length !== 2 || !bounds.every((point) =>
    Array.isArray(point) && point.length === 2 && point.every(Number.isFinite)
  )) {
    throw new Error('Slope overlay returned invalid geographic bounds')
  }
  const [[south, west], [north, east]] = bounds as SlopeBounds
  if (south >= north || west >= east) throw new Error('Slope overlay returned invalid geographic bounds')
  return [[south, west], [north, east]]
}

export function latestCompletedReconstructionId(jobs: Job[], sessionId: number | null) {
  return jobs.find((job) => job.session_id === sessionId && job.status === 'complete')?.id ?? null
}

async function fetchSlopeOverlay(reconstructionId: number) {
  const response = await fetch(apiUrl(`/export/reconstructions/${reconstructionId}/slope`), {
    credentials: 'include',
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null
    throw new Error(typeof body?.detail === 'string' ? body.detail : `API error ${response.status}`)
  }
  return {
    blob: await response.blob(),
    bounds: parseSlopeBounds(response.headers.get('X-Slope-Bounds')),
  }
}

export function useSlopeOverlay(sessionId: number | null, enabled: boolean) {
  const jobs = useQuery<Job[]>({
    queryKey: ['jobs', 'map-slope', sessionId],
    queryFn: () => get<Job[]>('/jobs/?status=complete&limit=200'),
    enabled: enabled && sessionId !== null,
    staleTime: 30_000,
  })
  const reconstructionId = latestCompletedReconstructionId(jobs.data ?? [], sessionId)
  const overlay = useQuery({
    queryKey: ['slope-overlay', reconstructionId],
    queryFn: () => fetchSlopeOverlay(reconstructionId as number),
    enabled: enabled && reconstructionId !== null,
    staleTime: Infinity,
  })
  // The cache holds the blob, never the object URL: a URL revoked on unmount would
  // otherwise still be served from the cache on the next mount (#663).
  const data = useMemo(
    () => (overlay.data ? { imageUrl: URL.createObjectURL(overlay.data.blob), bounds: overlay.data.bounds } : undefined),
    [overlay.data],
  )
  useEffect(() => () => {
    if (data) URL.revokeObjectURL(data.imageUrl)
  }, [data])

  const noReconstruction = enabled && jobs.data !== undefined && reconstructionId === null
  return {
    ...overlay,
    data,
    error: noReconstruction ? new Error('No completed reconstruction is available for this session.') : overlay.error,
  }
}
