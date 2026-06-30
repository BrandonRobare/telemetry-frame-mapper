import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Panel } from '../../shared/components/Panel'
import GeneralSettings from './GeneralSettings'
import IngestSettings from './IngestSettings'
import MissionPlanningSettings from './MissionPlanningSettings'
import ReconstructionSettings from './ReconstructionSettings'
import SplatSettings from './SplatSettings'
import RenderExportSettings from './RenderExportSettings'
import { useResetSettings } from './api'
import { useToast } from '../../shared/hooks/useToast'
import { getUrlParam, setUrlParam } from '../../shared/hooks/useUrlState'
import ConfirmDialog from '../../shared/components/ConfirmDialog'

// ---------------------------------------------------------------------------
// Sub-nav definition
// ---------------------------------------------------------------------------

type SettingsSection =
  | 'general'
  | 'ingest'
  | 'mission'
  | 'reconstruction'
  | 'splat'
  | 'render'

interface SectionEntry {
  id: SettingsSection
  label: string
  description: string
}

const SECTIONS: SectionEntry[] = [
  { id: 'general',        label: 'General',              description: 'Theme, display prefs, storage paths' },
  { id: 'ingest',         label: 'Import & Ingest',      description: 'Thumbnail, filters, accepted files' },
  { id: 'mission',        label: 'Mission Planning',     description: 'Altitude, FOV, overlap, battery' },
  { id: 'reconstruction', label: 'Reconstruction',       description: 'COLMAP, SIFT, preset selection' },
  { id: 'splat',          label: 'Splat Training',       description: 'Gaussian splat training presets' },
  { id: 'render',         label: 'Rendering & Export',   description: 'Flythrough, LOD, thumbnail output' },
]

function renderSection(id: SettingsSection) {
  switch (id) {
    case 'general':        return <GeneralSettings />
    case 'ingest':         return <IngestSettings />
    case 'mission':        return <MissionPlanningSettings />
    case 'reconstruction': return <ReconstructionSettings />
    case 'splat':          return <SplatSettings />
    case 'render':         return <RenderExportSettings />
  }
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function SettingsTab() {
  const [active, setActive] = useState<SettingsSection>(() => {
    const fromUrl = getUrlParam('section')
    return SECTIONS.some((s) => s.id === fromUrl) ? (fromUrl as SettingsSection) : 'general'
  })
  const resetMutation = useResetSettings()
  const { addToast } = useToast()
  const [confirmResetOpen, setConfirmResetOpen] = useState(false)

  // Deep-link the settings section (e.g. ?tab=settings&section=reconstruction).
  useEffect(() => { setUrlParam('section', active) }, [active])

  function handleReset() {
    resetMutation.mutate(undefined, {
      onSuccess: () => {
        setConfirmResetOpen(false)
        addToast('Settings reset to defaults', 'success')
      },
      onError: (err: Error) => addToast(err.message || 'Reset failed', 'error'),
    })
  }

  return (
    <>
      <div className="flex flex-1 overflow-hidden" style={{ color: 'var(--text)' }}>
      {/* ---- Left sub-nav ---- */}
      <aside
        className="flex flex-col shrink-0 overflow-y-auto"
        style={{
          width: 220,
          background: 'var(--surface)',
          borderRight: '1px solid var(--border)',
          padding: '20px 0',
        }}
      >
        <p
          className="text-xs font-semibold uppercase"
          style={{
            color: 'var(--text-faint)',
            letterSpacing: '0.07em',
            padding: '0 16px 10px',
          }}
        >
          Settings
        </p>

        <nav style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '0 8px' }}>
          {SECTIONS.map((sec) => {
            const isActive = active === sec.id
            return (
              <button
                key={sec.id}
                onClick={() => setActive(sec.id)}
                data-testid={`settings-nav-${sec.id}`}
                className="text-left cursor-pointer border-none"
                style={{
                  padding: '8px 10px',
                  background: isActive ? 'var(--accent-soft)' : 'transparent',
                  color: isActive ? 'var(--accent-strong)' : 'var(--text-muted)',
                  borderLeft: isActive ? '2px solid var(--accent)' : '2px solid transparent',
                  fontSize: 13,
                  fontFamily: 'inherit',
                  fontWeight: isActive ? 500 : 400,
                  transition: 'background var(--dur) var(--ease), color var(--dur) var(--ease)',
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = 'var(--surface-2)'
                    e.currentTarget.style.color = 'var(--text)'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = 'transparent'
                    e.currentTarget.style.color = 'var(--text-muted)'
                  }
                }}
              >
                {sec.label}
              </button>
            )
          })}
        </nav>

        {/* Reset button at the bottom of nav */}
        <div style={{ marginTop: 'auto', padding: '20px 8px 0' }}>
          <button
            type="button"
            onClick={() => setConfirmResetOpen(true)}
            disabled={resetMutation.isPending}
            className="text-left cursor-pointer border-none w-full"
            style={{
              padding: '7px 10px',
              background: 'transparent',
              color: 'var(--danger)',
              fontSize: 12,
              fontFamily: 'inherit',
              opacity: resetMutation.isPending ? 0.5 : 1,
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--danger-soft)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            {resetMutation.isPending ? 'Resetting…' : 'Reset all to defaults'}
          </button>
        </div>
      </aside>

      {/* ---- Right content panel ---- */}
      <main className="flex flex-1 overflow-y-auto" style={{ padding: 32, background: 'var(--bg)' }}>
        <div style={{ maxWidth: 700, width: '100%' }}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={active}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            >
              {/* Section header */}
              <div style={{ marginBottom: 24 }}>
                <h2
                  className="text-lg font-semibold"
                  style={{ color: 'var(--text)', margin: '0 0 4px' }}
                >
                  {SECTIONS.find((s) => s.id === active)?.label}
                </h2>
                <p className="text-sm" style={{ color: 'var(--text-muted)', margin: 0 }}>
                  {SECTIONS.find((s) => s.id === active)?.description}
                </p>
              </div>

              <Panel>
                <div style={{ padding: 20 }}>
                  {renderSection(active)}
                </div>
              </Panel>
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
      </div>
      <ConfirmDialog
        open={confirmResetOpen}
        title="Reset all settings?"
        description="This restores every setting to its default value. The change cannot be undone."
        confirmLabel="Reset settings"
        danger
        loading={resetMutation.isPending}
        onConfirm={handleReset}
        onCancel={() => setConfirmResetOpen(false)}
      />
    </>
  )
}
