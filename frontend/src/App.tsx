import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useMapStore } from './shared/stores/mapStore'
import { useSettingsStore } from './features/settings/settingsStore'
import MapTab from './features/map/MapTab'
import GpsSyncTab from './features/gps-sync/GpsSyncTab'
import ReviewTab from './features/review/ReviewTab'
import ExportTab from './features/export/ExportTab'
import PlanTab from './features/plan/PlanTab'
import SessionLogTab from './features/session-log/SessionLogTab'
import ReconstructTab from './features/reconstruct/ReconstructTab'
import JobsTab from './features/jobs/JobsTab'
import StorageTab from './features/storage/StorageTab'
import SplatViewerTab from './features/splat/SplatViewerTab'
import CompareTab from './features/compare/CompareTab'
import SettingsTab from './features/settings/SettingsTab'
import { ToastStack } from './shared/components/ToastStack'
import ImportModal from './features/import/ImportModal'
import SessionPicker from './features/sessions/SessionPicker'
import { fadeSlide, tabTransition, easeOut } from './shared/motion'

type Tab =
  | 'map'
  | 'gps-sync'
  | 'review'
  | 'plan'
  | 'export'
  | 'session-log'
  | 'reconstruct'
  | 'jobs'
  | 'storage'
  | 'splat'
  | 'compare'
  | 'settings'

const TABS: { id: Tab; label: string }[] = [
  { id: 'map', label: 'Map' },
  { id: 'gps-sync', label: 'GPS Sync' },
  { id: 'review', label: 'Review' },
  { id: 'plan', label: 'Plan' },
  { id: 'export', label: 'Export' },
  { id: 'session-log', label: 'Session Log' },
  { id: 'reconstruct', label: 'Reconstruct' },
  { id: 'jobs', label: 'Jobs' },
  { id: 'storage', label: 'Storage' },
  { id: 'splat', label: 'Splat Viewer' },
  { id: 'compare', label: 'Compare' },
  { id: 'settings', label: 'Settings' },
]

/** Framing/target mark — fits a mapping + telemetry tool, replaces the emoji logo. */
function LogoMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="var(--accent-soft)" stroke="var(--accent)" strokeWidth="1.5" />
      <circle cx="12" cy="12" r="2.4" fill="var(--accent)" />
      <path d="M12 4.5v2M12 17.5v2M4.5 12h2M17.5 12h2" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

function renderTab(tab: Tab) {
  switch (tab) {
    case 'map': return <MapTab />
    case 'gps-sync': return <GpsSyncTab />
    case 'review': return <ReviewTab />
    case 'plan': return <PlanTab />
    case 'export': return <ExportTab />
    case 'session-log': return <SessionLogTab />
    case 'reconstruct': return <ReconstructTab />
    case 'jobs': return <JobsTab />
    case 'storage': return <StorageTab />
    case 'splat': return <SplatViewerTab />
    case 'compare': return <CompareTab />
    case 'settings': return <SettingsTab />
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>(() => {
    const { defaultTab, lastActiveTab } = useSettingsStore.getState()
    const initialTab = lastActiveTab ?? defaultTab
    return TABS.some((t) => t.id === initialTab) ? (initialTab as Tab) : 'map'
  })
  const [showImport, setShowImport] = useState(false)
  const { requestedTab, setRequestedTab } = useMapStore()
  const setLastActiveTab = useSettingsStore((s) => s.setLastActiveTab)

  const selectTab = useCallback((tab: Tab) => {
    setActiveTab(tab)
    setLastActiveTab(tab)
  }, [setLastActiveTab])

  useEffect(() => {
    if (!requestedTab || !TABS.some((t) => t.id === requestedTab)) return

    queueMicrotask(() => {
      selectTab(requestedTab as Tab)
      setRequestedTab(null)
    })
  }, [requestedTab, selectTab, setRequestedTab])

  return (
    <div className="flex flex-col" style={{ height: '100vh', background: 'var(--bg)' }}>
      {/* Nav bar */}
      <nav
        className="flex items-stretch shrink-0"
        style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)', height: 44 }}
      >
        {/* Logo */}
        <div className="flex items-center gap-2 shrink-0" style={{ padding: '0 20px 0 16px' }}>
          <LogoMark />
          <span className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
            Frame Mapper
          </span>
        </div>

        {/* Tabs */}
        <div className="flex flex-1">
          {TABS.map((tab) => {
            const active = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => selectTab(tab.id)}
                className="relative px-4 text-sm cursor-pointer border-none bg-transparent h-full"
                style={{
                  color: active ? 'var(--text)' : 'var(--text-muted)',
                  fontFamily: 'inherit',
                  transition: 'color var(--dur) var(--ease)',
                }}
              >
                {tab.label}
                {active && (
                  <motion.div
                    layoutId="activeTabUnderline"
                    style={{
                      position: 'absolute',
                      left: 8,
                      right: 8,
                      bottom: 0,
                      height: 2,
                      borderRadius: 2,
                      background: 'var(--accent)',
                    }}
                    transition={{ duration: 0.22, ease: easeOut }}
                  />
                )}
              </button>
            )
          })}
        </div>

        {/* Session picker */}
        <div className="flex items-center shrink-0" style={{ padding: '0 8px', borderLeft: '1px solid var(--border)' }}>
          <SessionPicker onImport={() => setShowImport(true)} />
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2 shrink-0 pr-4">
          <button
            onClick={() => setShowImport(true)}
            className="text-sm rounded cursor-pointer border-none"
            style={{
              padding: '5px 14px',
              background: 'var(--accent-strong)',
              color: '#FFFDF7',
              fontFamily: 'inherit',
              transition: 'background var(--dur) var(--ease)',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--accent-hover)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--accent-strong)')}
          >
            + Import
          </button>
        </div>
      </nav>

      {/* Tab content */}
      <div className="flex flex-1 overflow-hidden">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={activeTab}
            className="flex flex-1 overflow-hidden"
            variants={fadeSlide}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={tabTransition}
          >
            {renderTab(activeTab)}
          </motion.div>
        </AnimatePresence>
      </div>
      <ToastStack />
      <ImportModal open={showImport} onClose={() => setShowImport(false)} />
    </div>
  )
}
