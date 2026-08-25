import { useQuery } from '@tanstack/react-query'
import { useMapStore } from '../../shared/stores/mapStore'
import { useSession } from '../map/hooks/useSession'
import { useQuickReport } from '../map/hooks/useQuickReport'
import { useCoverageResult } from '../map/hooks/useCoverageResult'
import { get } from '../../shared/api/client'
import { isLiveReconstructionStatus } from '../../shared/api/reconstructionStatusEvents'
import type { Job } from '../../types/api'
import { deriveStageStates } from '../../shared/pipeline/stages'
import PipelineOverview from './PipelineOverview'
import RapidQACard from './RapidQACard'
import ReconstructionLogo3D from '../hero/ReconstructionLogo3D'
import LogoMark from '../../shared/components/LogoMark'
import GlassSurface from '../../shared/components/GlassSurface'
import CornerTicks from '../../shared/components/CornerTicks'
import Button from '../../shared/components/Button'

interface Props {
  onImport?: () => void
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '10px 14px',
      }}
    >
      <div className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-display)' }}>{label}</div>
      <div className="font-semibold" style={{ fontFamily: 'var(--font-mono)', fontSize: 18, color: 'var(--accent-strong)', marginTop: 2 }}>
        {value}
      </div>
    </div>
  )
}

export default function OverviewTab({ onImport }: Props) {
  const selectedSessionId = useMapStore((s) => s.selectedSessionId)
  const { data: session } = useSession(selectedSessionId)
  const { data: coverage } = useCoverageResult(selectedSessionId)
  const { data: quickReport } = useQuickReport(selectedSessionId)
  const { data: jobs = [] } = useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: () => get<Job[]>('/jobs/'),
    refetchInterval: (q) => {
      const js = (q.state.data ?? []) as Job[]
      return js.some((j) => isLiveReconstructionStatus(j.status)) ? 3000 : false
    },
  })

  const latest = jobs
    .filter((j) => j.session_id === selectedSessionId)
    .sort((a, b) => b.id - a.id)[0]
  const states = deriveStageStates({ session, reconstruction: latest ?? null, coverage })
  const covPct = coverage?.coverage_pct ?? null

  return (
    <div className="flex-1 overflow-y-auto" style={{ background: 'var(--bg)' }}>
      <div className="fm-overview-shell" style={{ maxWidth: 920, margin: '0 auto', padding: '24px 24px 48px' }}>
        {/* Hero band: 3D logo over the earthy backdrop */}
        <div
          className="fm-overview-hero tg-topo-backdrop relative overflow-hidden"
          style={{ height: 250, border: '1px solid var(--border-strong)' }}
        >
          <CornerTicks size={10} inset={5} label={session ? session.name : 'no session'} />
          <ReconstructionLogo3D stageStates={states} className="absolute inset-0 w-full h-full" />
          <div className="fm-overview-copy absolute" style={{ left: 26, top: 26, maxWidth: 360 }}>
            <div className="flex items-center gap-2">
              <LogoMark size={26} />
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text)' }}>
                Telemetry Frame Mapper
              </span>
            </div>
            <p className="mt-2" style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.55 }}>
              A drone flight becomes a measurable, explorable 3D site. One pipeline, end to end.
            </p>
          </div>
        </div>

        {/* Rapid QA card */}
        {quickReport && (
          <div className="mt-5">
            <RapidQACard report={quickReport} />
          </div>
        )}

        {/* The pipeline */}
        <GlassSurface interactive={false} refraction={false} radius={0} className="mt-5" style={{ padding: '20px 22px', border: '1px solid var(--border)' }}>
          <div className="flex items-baseline justify-between mb-4">
            <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 16, color: 'var(--text)', margin: 0 }}>
              The pipeline
            </h2>
            <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
              {session ? `Session · ${session.name}` : 'No session yet'}
            </span>
          </div>
          <PipelineOverview stageStates={states} variant="full" />
        </GlassSurface>

        {/* Session summary or import CTA */}
        {session ? (
          <div
            className="mt-5 grid gap-3"
            style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}
          >
            <Stat label="Frames" value={session.photo_count} />
            <Stat label="Usable" value={session.usable_count} />
            <Stat label="Coverage" value={covPct !== null ? `${covPct.toFixed(0)}%` : '—'} />
            <Stat label="Reconstruction" value={latest ? latest.status.replace('running_', '') : 'none'} />
          </div>
        ) : (
          <div
            className="fm-overview-cta mt-5 flex items-center justify-between gap-4"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '18px 20px' }}
          >
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--text)' }}>
                Start with a flight
              </div>
              <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 2 }}>
                Import a DJI video + frames to light up the pipeline.
              </div>
            </div>
            <div className="fm-overview-cta-actions flex items-center gap-3 shrink-0">
              <Button onClick={onImport}>Import a flight</Button>
              <span style={{ fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>.jpg frames in a folder</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
