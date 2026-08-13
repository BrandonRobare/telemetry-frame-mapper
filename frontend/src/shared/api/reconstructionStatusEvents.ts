import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiUrl } from './client'
import type { Job, Reconstruction } from '../../types/api'

const LIVE_STATUSES = new Set<Job['status']>(['pending', 'running_colmap', 'running_gsplat', 'cancelling'])

export function isLiveReconstructionStatus(status: Job['status']) {
  return LIVE_STATUSES.has(status)
}

function applyReconstructionStatus(job: Job, status: Reconstruction): Job {
  return {
    ...job,
    status: status.status,
    preset: status.preset,
    progress_pct: status.progress_pct,
    step: status.step,
    frames_used: status.frames_used,
    error_msg: status.error_msg,
  }
}

export function useReconstructionStatusEvents(
  jobs: Job[] | undefined,
  onConnectedIdsChange: (ids: ReadonlySet<number>) => void
) {
  const qc = useQueryClient()
  const idsKey = (jobs ?? [])
    .filter((job) => isLiveReconstructionStatus(job.status))
    .map((job) => job.id)
    .sort((a, b) => a - b)
    .join(',')

  useEffect(() => {
    const ids = idsKey ? idsKey.split(',').map(Number) : []
    if (ids.length === 0) {
      onConnectedIdsChange(new Set())
      return
    }

    const connected = new Set<number>()
    const publishConnected = () => onConnectedIdsChange(new Set(connected))
    const sources = ids.map((id) => {
      const source = new EventSource(apiUrl(`/reconstruction/${id}/status/events`), { withCredentials: true })
      source.onopen = () => {
        connected.add(id)
        publishConnected()
      }
      source.onerror = () => {
        connected.delete(id)
        publishConnected()
      }
      source.addEventListener('status', (event) => {
        const status = JSON.parse((event as MessageEvent).data) as Reconstruction
        qc.setQueriesData<Job[]>({ queryKey: ['jobs'] }, (old) => {
          if (!old) return old
          return old.map((job) => (job.id === id ? applyReconstructionStatus(job, status) : job))
        })
        if (!isLiveReconstructionStatus(status.status)) {
          qc.invalidateQueries({ queryKey: ['jobs'] })
        }
      })
      return source
    })

    return () => {
      sources.forEach((source) => source.close())
      onConnectedIdsChange(new Set())
    }
  }, [idsKey, onConnectedIdsChange, qc])
}
