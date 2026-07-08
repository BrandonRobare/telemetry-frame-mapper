import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import { isLiveReconstructionStatus } from '../api/reconstructionStatusEvents'
import { useToast } from '../hooks/useToast'
import type { Job } from '../../types/api'
import {
  detectJobTransitions,
  formatJobNotification,
  nextStatusMap,
  shouldShowDesktopNotification,
  type JobNotificationContent,
} from './jobNotifications'

function desktopNotify(content: JobNotificationContent) {
  // Degrade silently: no Notification API, no permission, or a construction
  // error (e.g. some platforms require a service worker) all just skip.
  try {
    if (typeof Notification === 'undefined') return
    if (!shouldShowDesktopNotification(document.hidden, Notification.permission)) return
    new Notification(content.title, { body: content.body })
  } catch {
    /* ignore */
  }
}

function requestPermissionForLiveJobs(jobs: Job[], alreadyAsked: { current: boolean }) {
  try {
    if (typeof Notification === 'undefined') return
    if (Notification.permission !== 'default' || alreadyAsked.current) return
    if (!jobs.some((j) => isLiveReconstructionStatus(j.status))) return
    alreadyAsked.current = true
    void Notification.requestPermission()
  } catch {
    /* ignore */
  }
}

/**
 * App-shell hook (issue #380): watches the shared `['jobs']` query — kept
 * fresh by usePipelineStatus polling and the reconstruction SSE stream — and
 * fires an in-app toast plus, when the tab is hidden and permission is
 * granted, a browser desktop notification whenever a job transitions from a
 * live status to complete/failed/cancelled.
 */
export function useJobCompletionNotifications() {
  const addToast = useToast((s) => s.addToast)
  const previousStatuses = useRef<Map<number, Job['status']> | null>(null)
  const permissionAsked = useRef(false)

  // Same key + fetch as usePipelineStatus; react-query dedupes the observers,
  // so this adds no extra polling while jobs run.
  const { data: jobs } = useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: () => get<Job[]>('/jobs/'),
    refetchInterval: (q) => {
      const js = (q.state.data ?? []) as Job[]
      return js.some((j) => isLiveReconstructionStatus(j.status)) ? 3000 : false
    },
  })

  useEffect(() => {
    if (!jobs) return
    const previous = previousStatuses.current
    previousStatuses.current = nextStatusMap(jobs)
    // First snapshot (page load / refresh): record statuses, never notify.
    if (!previous) return

    requestPermissionForLiveJobs(jobs, permissionAsked)

    for (const { job, outcome } of detectJobTransitions(previous, jobs)) {
      const content = formatJobNotification(job, outcome)
      addToast(`${content.title} — ${content.body}`, content.toastType)
      desktopNotify(content)
    }
  }, [jobs, addToast])
}
