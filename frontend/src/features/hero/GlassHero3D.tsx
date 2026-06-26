import GlassSurface from '../../shared/components/GlassSurface'
import Button from '../../shared/components/Button'
import LogoMark from '../../shared/components/LogoMark'
import ReconstructionLogo3D from './ReconstructionLogo3D'
import PipelineOverview from '../overview/PipelineOverview'
import { deriveStageStates } from '../../shared/pipeline/stages'

interface Props {
  onImport?: () => void
}

/* The Map no-session landing. The earthy backdrop + 3D hex-prism logo (which
   color-tracks pipeline progress) replace the old rotating icosahedron, and a
   compact pipeline overview replaces the marketing catchphrase. With no session
   loaded the pipeline reads "Import" as the active next step. */
export default function GlassHero3D({ onImport }: Props) {
  const states = deriveStageStates({ session: null })

  return (
    <div className="tg-topo-backdrop relative flex-1 overflow-hidden flex items-center" style={{ minHeight: 0 }}>
      <ReconstructionLogo3D stageStates={states} className="absolute inset-0 w-full h-full" />

      <div className="relative z-10 w-full flex justify-start" style={{ paddingLeft: '5%', paddingRight: '5%' }}>
        <GlassSurface intensity={0.8} radius={0} className="p-7" style={{ maxWidth: 500, width: '100%', border: '1px solid var(--glass-border)' }}>
          <div className="flex items-center gap-2 mb-3">
            <LogoMark size={24} />
            <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text)' }}>
              Telemetry Frame Mapper
            </span>
          </div>
          <PipelineOverview stageStates={states} variant="compact" />
          <div className="mt-5 flex items-center gap-3">
            <Button onClick={onImport}>Import a flight</Button>
            <span className="text-xs" style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
              .jpg frames in a folder
            </span>
          </div>
        </GlassSurface>
      </div>
    </div>
  )
}
