import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useMapStore } from '../../shared/stores/mapStore'
import { useSessions } from '../sessions/useSessions'
import { useSession } from '../map/hooks/useSession'
import { useQuickReport } from '../map/hooks/useQuickReport'
import { usePipelineStatus } from '../../shared/pipeline/usePipelineStatus'
import { get } from '../../shared/api/client'
import { formatEta } from '../../shared/time'
import { PIPELINE_STAGES } from '../../shared/pipeline/stages'
import type { Job } from '../../types/api'
import LogoMark from '../../shared/components/LogoMark'
import { Skeleton, SkeletonText } from '../../shared/components/Skeleton'
import RapidQACard from '../overview/RapidQACard'
import { selectJobsForSession, selectRunningJobs } from './jobsSummary'
import { prioritizeWarnings } from './warningPriority'

const JOB_STATUS_LABEL: Record<string, string> = {
  pending: 'Queued',
  running_colmap: 'Aligning',
  running_gsplat: 'Training',
  running_remote: 'Remote worker',
  cancelling: 'Cancelling',
  cancelled: 'Cancelled',
  complete: 'Complete',
  failed: 'Failed',
}

function useAllJobs() {
  return useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: () => get<Job[]>('/jobs/'),
    refetchInterval: (q) => {
      const js = (q.state.data ?? []) as Job[]
      return selectRunningJobs(js).length > 0 ? 3000 : 10_000
    },
  })
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginTop: 16 }}>
      <h2
        style={{
          fontFamily: 'var(--font-display)',
          fontWeight: 600,
          fontSize: 12,
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
          color: 'var(--text-faint)',
          margin: '0 0 8px',
        }}
      >
        {title}
      </h2>
      {children}
    </section>
  )
}

function StatChip({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <div
      style={{
        flex: '1 1 84px',
        minWidth: 84,
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        background: 'var(--surface-2)',
        padding: '6px 10px',
      }}
    >
      <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-display)' }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 15, fontWeight: 600, color: tone ?? 'var(--accent-strong)' }}>
        {value}
      </div>
    </div>
  )
}

function JobRow({ job }: { job: Job }) {
  const eta = formatEta(job.started_at, job.progress_pct)
  const label = JOB_STATUS_LABEL[job.status] ?? job.status
  const failed = job.status === 'failed'
  return (
    <div
      style={{
        border: `1px solid ${failed ? 'var(--danger-accent)' : 'var(--border)'}`,
        borderRadius: 'var(--radius-md)',
        background: 'var(--surface)',
        padding: '10px 12px',
        marginBottom: 8,
      }}
    >
      <div className="flex items-center justify-between" style={{ marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Session {job.session_id} · #{job.id}
        </span>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: failed ? 'var(--danger)' : 'var(--accent-strong)',
            fontFamily: 'var(--font-display)',
          }}
        >
          {label}
        </span>
      </div>
      <div style={{ height: 4, borderRadius: 2, background: 'var(--surface-2)', overflow: 'hidden' }}>
        <div
          style={{
            height: '100%',
            borderRadius: 2,
            background: failed ? 'var(--danger-accent)' : 'var(--accent)',
            width: `${job.progress_pct}%`,
            transition: 'width 0.5s ease',
          }}
        />
      </div>
      <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: '6px 0 0' }}>
        {job.progress_pct.toFixed(0)}% · {job.step || 'Initializing…'}
        {eta && ` · ${eta}`}
      </p>
    </div>
  )
}

/* Phone-sized quick-check view (issue #364) — a single-column, read-only
   snapshot of session status, the post-landing quick QA report, and running
   jobs, for an operator glancing at their phone in the field. Lives at
   /mobile (or /m) and bypasses the desktop tab shell entirely, mirroring how
   ShareViewer bypasses it for /view/share/. Reuses the same hooks/queries as
   the desktop Overview and Jobs tabs — no new endpoints. */
export default function MobileQuickCheck() {
  const { data: sessions, isLoading: sessionsLoading } = useSessions(null)
  const selectedSessionId = useMapStore((s) => s.selectedSessionId)
  const setSession = useMapStore((s) => s.setSession)
  const { data: session } = useSession(selectedSessionId)
  const { data: quickReport, isLoading: reportLoading } = useQuickReport(selectedSessionId)
  const status = usePipelineStatus(selectedSessionId)
  const { data: allJobs = [] } = useAllJobs()

  // Auto-select a session so the field operator isn't left staring at an empty
  // page — mirrors SessionPicker's behavior on the desktop shell (#364).
  useEffect(() => {
    if (!sessions || sessions.length === 0) return
    if (selectedSessionId === null || !sessions.some((s) => s.id === selectedSessionId)) {
      setSession(sessions[0].id)
    }
  }, [sessions, selectedSessionId, setSession])

  const sessionJobs = selectJobsForSession(allJobs, selectedSessionId)
  const runningJobs = selectRunningJobs(allJobs)
  const otherRunningJobs = runningJobs.filter((j) => j.session_id !== selectedSessionId)

  const stageIndex = status.activeStage
    ? PIPELINE_STAGES.findIndex((s) => s.key === status.activeStage!.key) + 1
    : PIPELINE_STAGES.length

  return (
    <div
      className="fm-mobile-quickcheck"
      style={{
        minHeight: '100vh',
        background: 'var(--bg)',
        color: 'var(--text)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <header
        className="flex items-center gap-2 shrink-0"
        style={{
          height: 48,
          padding: '0 14px',
          background: 'var(--surface)',
          borderBottom: '1px solid var(--border)',
          position: 'sticky',
          top: 0,
          zIndex: 5,
        }}
      >
        <LogoMark size={22} stageStates={selectedSessionId !== null ? status.states : undefined} />
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14 }}>
          Quick Check
        </span>
        <a
          href="/"
          className="text-xs no-underline"
          style={{ marginLeft: 'auto', color: 'var(--text-muted)' }}
        >
          Full app →
        </a>
      </header>

      <main className="flex-1" style={{ padding: '14px 14px 32px', maxWidth: 480, margin: '0 auto', width: '100%' }}>
        {/* Session picker — compact, single select */}
        <Section title="Session">
          {sessionsLoading ? (
            <Skeleton height={36} radius="var(--radius-sm)" />
          ) : !sessions || sessions.length === 0 ? (
            <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0 }}>
              No sessions imported yet. Use the full app to import a flight.
            </p>
          ) : (
            <select
              aria-label="Select session"
              value={selectedSessionId ?? ''}
              onChange={(e) => setSession(e.target.value ? parseInt(e.target.value, 10) : null)}
              style={{
                width: '100%',
                padding: '9px 10px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border)',
                background: 'var(--surface)',
                color: 'var(--text)',
                fontSize: 14,
              }}
            >
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          )}
        </Section>

        {selectedSessionId !== null && session && (
          <>
            {/* Session status: import progress, photo/usable counts, pipeline stage */}
            <Section title="Session status">
              <div className="flex flex-wrap" style={{ gap: 8, marginBottom: 8 }}>
                <StatChip label="Frames" value={session.photo_count} />
                <StatChip label="Usable" value={session.usable_count} />
                <StatChip
                  label="Coverage"
                  value={status.coverage?.coverage_pct != null ? `${status.coverage.coverage_pct.toFixed(0)}%` : '—'}
                />
                <StatChip label="Progress" value={`${status.progress}%`} tone="var(--success)" />
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Stage {stageIndex}/{PIPELINE_STAGES.length} ·{' '}
                <span style={{ color: 'var(--accent-strong)', fontWeight: 600 }}>
                  {status.activeStage ? status.activeStage.name : 'Complete'}
                </span>
              </div>
            </Section>

            {/* Post-landing quick QA summary — reuses RapidQACard + useQuickReport,
                but with GPS-lock warnings surfaced first (tight vertical space). */}
            <Section title="Quick QA">
              {reportLoading ? (
                <SkeletonText lines={3} />
              ) : quickReport ? (
                <RapidQACard
                  report={{ ...quickReport, warnings: prioritizeWarnings(quickReport.warnings, 4) }}
                  compact
                />
              ) : (
                <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0 }}>
                  No quick report available for this session yet.
                </p>
              )}
            </Section>

            {/* This session's jobs */}
            <Section title="This session's jobs">
              {sessionJobs.length === 0 ? (
                <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0 }}>No jobs run yet.</p>
              ) : (
                sessionJobs.slice(0, 5).map((job) => <JobRow key={job.id} job={job} />)
              )}
            </Section>
          </>
        )}

        {/* Other running jobs across sessions */}
        {otherRunningJobs.length > 0 && (
          <Section title="Other running jobs">
            {otherRunningJobs.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </Section>
        )}
      </main>
    </div>
  )
}
