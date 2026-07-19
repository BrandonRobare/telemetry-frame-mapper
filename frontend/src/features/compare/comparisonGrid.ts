import type { Job } from '../../types/api'

/** Return the distinct reconstructions that make up the 2–4-up comparison grid. */
export function comparisonGridJobs(
  jobs: Job[],
  ids: Array<number | null>,
): Job[] {
  const byId = new Map(jobs.map((job) => [job.id, job]))
  const seen = new Set<number>()

  return ids.flatMap((id) => {
    if (id === null || seen.has(id)) return []
    const job = byId.get(id)
    if (!job) return []
    seen.add(id)
    return [job]
  })
}
