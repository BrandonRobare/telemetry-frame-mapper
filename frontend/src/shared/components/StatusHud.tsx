import { PIPELINE_STAGES, stageColor } from '../pipeline/stages'
import type { PipelineStatus } from '../pipeline/usePipelineStatus'

interface StatusHudProps {
  status: PipelineStatus
  /** Jump to a pipeline stage's tab. */
  onGoToTab: (tab: string) => void
}

/* A slim telemetry strip under the nav — drone-instrument readouts in mono.
   Surfaces the current stage, whole-pipeline progress, frame counts and
   coverage at a glance, so the operator never has to hunt across tabs. */
export function StatusHud({ status, onGoToTab }: StatusHudProps) {
  const { session, coverage, latest, states, activeStage, progress } = status
  if (!session) return null

  const stageIndex = activeStage ? PIPELINE_STAGES.findIndex((s) => s.key === activeStage.key) + 1 : PIPELINE_STAGES.length
  const dot = stageColor(activeStage ? states[activeStage.key] : 'done')
  const covPct = coverage?.coverage_pct ?? null
  const RECON_LABELS: Record<string, string> = {
    pending: 'Queued', running_colmap: 'Aligning', running_gsplat: 'Training', complete: 'Complete', failed: 'Failed',
  }
  const recon = latest ? (RECON_LABELS[latest.status] ?? latest.status.replace('running_', '')) : 'none'

  const readout = (label: string, value: string, color?: string) => (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
      <span style={{ color: 'var(--text-faint)', letterSpacing: '0.06em' }}>{label}</span>
      <span style={{ color: color ?? 'var(--text)', fontWeight: 500 }}>{value}</span>
    </span>
  )

  return (
    <div
      className="flex items-center shrink-0 tg-noscrollbar"
      style={{
        height: 30,
        gap: 16,
        padding: '0 14px',
        background: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
        fontFamily: 'var(--font-mono)',
        fontSize: 11.5,
        overflowX: 'auto',
        whiteSpace: 'nowrap',
      }}
    >
      {/* current stage — click to jump */}
      <button
        onClick={() => activeStage && onGoToTab(activeStage.tab)}
        className="flex items-center cursor-pointer border-none bg-transparent"
        style={{ gap: 7, color: 'var(--text)', fontFamily: 'inherit', fontSize: 'inherit', padding: 0 }}
        title={activeStage ? `Go to ${activeStage.name}` : 'Pipeline complete'}
      >
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: dot, boxShadow: `0 0 0 3px color-mix(in srgb, ${dot} 28%, transparent)` }} />
        <span style={{ color: 'var(--text-faint)', letterSpacing: '0.06em' }}>STAGE</span>
        <span style={{ fontWeight: 500 }}>{stageIndex}/{PIPELINE_STAGES.length}</span>
        <span style={{ color: 'var(--accent-strong)', fontWeight: 500 }}>{activeStage ? activeStage.name : 'Complete'}</span>
      </button>

      {/* whole-pipeline progress bar */}
      <span className="flex items-center" style={{ gap: 7, minWidth: 120 }}>
        <span style={{ position: 'relative', width: 80, height: 4, background: 'var(--surface-2)', borderRadius: 999, overflow: 'hidden' }}>
          <span style={{ position: 'absolute', inset: 0, width: `${progress}%`, background: 'var(--sage)', transition: 'width var(--dur-slow) var(--ease)' }} />
        </span>
        <span style={{ color: 'var(--success)', fontWeight: 500 }}>{progress}%</span>
      </span>

      <span aria-hidden style={{ width: 1, height: 14, background: 'var(--border)' }} />

      {readout('FRAMES', String(session.photo_count))}
      {readout('USABLE', String(session.usable_count), 'var(--success)')}
      {readout('COVERAGE', covPct !== null ? `${covPct.toFixed(0)}%` : '—', covPct !== null ? 'var(--success)' : 'var(--text-muted)')}
      {readout('RECON', recon, latest?.status === 'failed' ? 'var(--danger)' : undefined)}

      <span style={{ marginLeft: 'auto', color: 'var(--text-faint)', letterSpacing: '0.04em', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {session.name}
      </span>
    </div>
  )
}

export default StatusHud
