import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import { get, post, patch } from './client'
import { importProgressRefetchInterval } from './importProgress'
import { useToast } from '../hooks/useToast'
import type { Session, Image } from '../../types/api'

export function useRunCoverage() {
  const qc = useQueryClient()
  const { addToast } = useToast()
  return useMutation({
    mutationFn: ({ sessionId, targetAreaId }: { sessionId: number; targetAreaId: number }) =>
      post(`/coverage/run?session_id=${sessionId}&target_area_id=${targetAreaId}`),
    onSuccess: (_, { sessionId }) => {
      qc.invalidateQueries({ queryKey: ['coverage', sessionId] })
      addToast('Coverage analysis complete', 'success')
    },
    onError: (e: Error) => addToast(e.message, 'error'),
  })
}

export function useApplyFlightSync() {
  const qc = useQueryClient()
  const { addToast } = useToast()
  return useMutation({
    mutationFn: ({ sessionId, offsetS, toleranceS }: { sessionId: number; offsetS: number; toleranceS: number }) =>
      post(`/flight-logs/apply?session_id=${sessionId}&offset_s=${offsetS}&tolerance_s=${toleranceS}`),
    onSuccess: (_, { sessionId }) => {
      qc.invalidateQueries({ queryKey: ['session', sessionId] })
      qc.invalidateQueries({ queryKey: ['footprints', sessionId] })
      addToast('GPS sync applied', 'success')
    },
    onError: (e: Error) => addToast(e.message, 'error'),
  })
}

export function useFlagImage() {
  const qc = useQueryClient()
  const { addToast } = useToast()
  return useMutation({
    mutationFn: ({ id, flag }: { id: number; flag: string }) =>
      patch<Image>(`/images/${id}`, { flag }),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ['images', updated.session_id] })
    },
    onError: (e: Error) => addToast(e.message, 'error'),
  })
}

export function useGeneratePlan() {
  const qc = useQueryClient()
  const { addToast } = useToast()
  return useMutation({
    mutationFn: (body: { target_area_id: number; altitude_ft: number; side_overlap_pct: number; forward_overlap_pct: number }) =>
      post<{ id: number; lanes_geojson: string }>('/plans/generate', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plans'] })
      addToast('Mission plan generated', 'success')
    },
    onError: (e: Error) => addToast(e.message, 'error'),
  })
}

export function useImportSession() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [importingSessionId, setImportingSessionId] = useState<number | null>(null)

  const progressQuery = useQuery({
    queryKey: ['session-progress', importingSessionId],
    queryFn: () => get<{
      processed: number
      total: number
      status: 'running' | 'done' | 'error'
      error?: string
    }>(
      `/sessions/${importingSessionId}/progress`
    ),
    enabled: importingSessionId !== null,
    refetchInterval: (query) => importProgressRefetchInterval(query.state.data?.status),
  })

  useEffect(() => {
    const status = progressQuery.data?.status
    if (!status) return
    if (status === 'done') {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      addToast('Session imported successfully', 'success')
      queueMicrotask(() => setImportingSessionId(null))
    } else if (status === 'error') {
      addToast(progressQuery.data?.error || 'Import failed', 'error')
      queueMicrotask(() => setImportingSessionId(null))
    }
  }, [progressQuery.data?.status, progressQuery.data?.error, queryClient, addToast])

  const mutation = useMutation({
    mutationFn: (body: { folder_path: string; name: string }) =>
      post<Session>('/sessions/import', body),
    onSuccess: (session) => {
      setImportingSessionId(session.id)
    },
    onError: () => addToast('Failed to start import', 'error'),
  })

  return {
    ...mutation,
    progress: progressQuery.data ?? null,
    isImporting: importingSessionId !== null,
  }
}
