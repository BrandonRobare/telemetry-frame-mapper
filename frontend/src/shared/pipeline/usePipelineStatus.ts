import { useQuery } from '@tanstack/react-query'
import type { Job } from '../../types/api'
import { get } from '../api/client'
import { useSession } from '../../features/map/hooks/useSession'
import { useCoverageResult } from '../../features/map/hooks/useCoverageResult'
import {
  PIPELINE_STAGES,
  deriveStageStates,
  type PipelineStage,
  type StageKey,
  type StageState,
} from './stages'

const ACTIVE = ['pending', 'running_colmap', 'running_gsplat']

export interface PipelineStatus {
  session: ReturnType<typeof useSession>['data']
  coverage: ReturnType<typeof useCoverageResult>['data']
  latest: Job | null
  states: Record<StageKey, StageState>
  activeStage: PipelineStage | null
  doneCount: number
  /** Whole-pipeline completion, 0..100. */
  progress: number
}

/* Single source of pipeline status for the app shell (nav hex meter + telemetry
   HUD). Mirrors OverviewTab's data wiring; react-query dedupes the shared keys. */
export function usePipelineStatus(sessionId: number | null): PipelineStatus {
  const { data: session } = useSession(sessionId)
  const { data: coverage } = useCoverageResult(sessionId)
  const { data: jobs = [] } = useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: () => get<Job[]>('/jobs/'),
    refetchInterval: (q) => {
      const js = (q.state.data ?? []) as Job[]
      return js.some((j) => ACTIVE.includes(j.status)) ? 3000 : false
    },
  })

  const latest =
    jobs.filter((j) => j.session_id === sessionId).sort((a, b) => b.id - a.id)[0] ?? null
  const states = deriveStageStates({ session, reconstruction: latest, coverage })
  const activeStage = PIPELINE_STAGES.find((s) => states[s.key] === 'active') ?? null
  const doneCount = PIPELINE_STAGES.filter((s) => states[s.key] === 'done').length
  const progress = Math.round((doneCount / PIPELINE_STAGES.length) * 100)

  return { session, coverage, latest, states, activeStage, doneCount, progress }
}
