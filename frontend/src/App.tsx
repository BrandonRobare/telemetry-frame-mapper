import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useMapStore } from './shared/stores/mapStore'
import { useSettingsStore } from './features/settings/settingsStore'
import OverviewTab from './features/overview/OverviewTab'
import LogoMark from './shared/components/LogoMark'
import MapTab from './features/map/MapTab'
import GpsSyncTab from './features/gps-sync/GpsSyncTab'
import ReviewTab from './features/review/ReviewTab'
import ExportTab from './features/export/ExportTab'
import PlanTab from './features/plan/PlanTab'
import SessionLogTab from './features/session-log/SessionLogTab'
import ChecklistTab from './features/checklist/ChecklistTab'
import ReconstructTab from './features/reconstruct/ReconstructTab'
import JobsTab from './features/jobs/JobsTab'
import StorageTab from './features/storage/StorageTab'
import SplatViewerTab from './features/splat/SplatViewerTab'
import CompareTab from './features/compare/CompareTab'
import SettingsTab from './features/settings/SettingsTab'
import { ToastStack } from './shared/components/ToastStack'
import { GlassFilters } from './shared/components/GlassFilters'
import ShareViewer from './features/share/ShareViewer'
import MobileQuickCheck from './features/mobile/MobileQuickCheck'
import { isMobileRoute } from './features/mobile/mobileRoute'
import { StatusHud } from './shared/components/StatusHud'
import { usePipelineStatus } from './shared/pipeline/usePipelineStatus'
import { useJobCompletionNotifications } from './shared/notifications/useJobCompletionNotifications'
import ImportModal from './features/import/ImportModal'
import SessionPicker from './features/sessions/SessionPicker'
import ProjectPicker from './features/sessions/ProjectPicker'
import { splatBloom, reducedFade, bloomTransition, easeOut } from './shared/motion'
import { getUrlParam, setUrlParam } from './shared/hooks/useUrlState'

type Tab =
  | 'overview'
  | 'map'
  | 'gps-sync'
  | 'review'
  | 'plan'
  | 'export'
  | 'session-log'
  | 'checklist'
  | 'reconstruct'
  | 'jobs'
  | 'storage'
  | 'splat'
  | 'compare'
  | 'settings'

// Ordered to follow the pipeline (Overview → … → Export), then auxiliary tools.
// A divider is drawn in the nav where the group changes (Law of Common Region).
const TABS: { id: Tab; label: string; group: 'pipeline' | 'tools' }[] = [
  { id: 'overview', label: 'Overview', group: 'pipeline' },
  { id: 'map', label: 'Map', group: 'pipeline' },
  { id: 'review', label: 'Review', group: 'pipeline' },
  { id: 'reconstruct', label: 'Reconstruct', group: 'pipeline' },
  { id: 'splat', label: 'Splat Viewer', group: 'pipeline' },
  { id: 'export', label: 'Export', group: 'pipeline' },
  { id: 'plan', label: 'Plan', group: 'tools' },
  { id: 'gps-sync', label: 'GPS Sync', group: 'tools' },
  { id: 'jobs', label: 'Jobs', group: 'tools' },
  { id: 'compare', label: 'Compare', group: 'tools' },
  { id: 'storage', label: 'Storage', group: 'tools' },
  { id: 'session-log', label: 'Session Log', group: 'tools' },
  { id: 'checklist', label: 'Field Checklist', group: 'tools' },
  { id: 'settings', label: 'Settings', group: 'tools' },
]

const PIPELINE_TABS = TABS.filter((t) => t.group === 'pipeline')
const TOOL_TABS = TABS.filter((t) => t.group === 'tools')

function renderTab(tab: Tab, onImport: () => void) {
  switch (tab) {
    case 'overview': return <OverviewTab onImport={onImport} />
    case 'map': return <MapTab onImport={onImport} />
    case 'gps-sync': return <GpsSyncTab />
    case 'review': return <ReviewTab />
    case 'plan': return <PlanTab />
    case 'export': return <ExportTab />
    case 'session-log': return <SessionLogTab />
    case 'checklist': return <ChecklistTab />
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
    const initialTab = getUrlParam('tab') ?? lastActiveTab ?? defaultTab
    return TABS.some((t) => t.id === initialTab) ? (initialTab as Tab) : 'overview'
  })
  const [showImport, setShowImport] = useState(false)
  const { requestedTab, setRequestedTab } = useMapStore()
  const selectedSessionId = useMapStore((s) => s.selectedSessionId)
  const selectedProjectId = useMapStore((s) => s.selectedProjectId)
  const status = usePipelineStatus(selectedSessionId)
  // Job-completion notifications (toast + desktop when tab is hidden), #380.
  useJobCompletionNotifications()
  const [toolsOpen, setToolsOpen] = useState(false)
  const toolActive = TOOL_TABS.some((t) => t.id === activeTab)
  const toolsBtnRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const reducedMotion = useSettingsStore((s) => s.reducedMotion)
  const setLastActiveTab = useSettingsStore((s) => s.setLastActiveTab)

  const selectTab = useCallback((tab: Tab) => {
    setActiveTab(tab)
    setLastActiveTab(tab)
    setUrlParam('tab', tab)
  }, [setLastActiveTab])

  // Keep the active tab linkable: reflect it in the URL and respond to
  // browser back/forward (or a hand-edited ?tab= param).
  useEffect(() => {
    setUrlParam('tab', activeTab)
    const onPop = () => {
      const fromUrl = getUrlParam('tab')
      if (fromUrl && TABS.some((t) => t.id === fromUrl)) setActiveTab(fromUrl as Tab)
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
    // Mount-only: subsequent URL writes flow through selectTab.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!requestedTab || !TABS.some((t) => t.id === requestedTab)) return

    queueMicrotask(() => {
      selectTab(requestedTab as Tab)
      setRequestedTab(null)
    })
  }, [requestedTab, selectTab, setRequestedTab])

  // Reflect the in-app "Reduced motion" setting onto the root so CSS (and the
  // glass effects) honor it, not just the OS-level prefers-reduced-motion.
  useEffect(() => {
    document.documentElement.setAttribute('data-reduced-motion', String(reducedMotion))
  }, [reducedMotion])

  // Focus the first item when the Tools dropdown opens (keyboard menu pattern).
  useEffect(() => {
    if (toolsOpen) menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
  }, [toolsOpen])

  function onToolsBtnKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setToolsOpen(true) }
    else if (e.key === 'Escape' && toolsOpen) { e.preventDefault(); setToolsOpen(false) }
  }
  function onMenuKeyDown(e: React.KeyboardEvent) {
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])
    const idx = items.indexOf(document.activeElement as HTMLElement)
    if (e.key === 'Escape') { e.preventDefault(); setToolsOpen(false); toolsBtnRef.current?.focus() }
    else if (e.key === 'ArrowDown') { e.preventDefault(); items[Math.min(idx + 1, items.length - 1)]?.focus() }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items[Math.max(idx - 1, 0)]?.focus() }
    else if (e.key === 'Home') { e.preventDefault(); items[0]?.focus() }
    else if (e.key === 'End') { e.preventDefault(); items[items.length - 1]?.focus() }
    else if (e.key === 'Tab') { setToolsOpen(false) }
  }

  return (
    <>
      {/* Public share viewer — strip operator UI entirely. */}
      {window.location.pathname.startsWith('/view/share/') ? (
        <ShareViewer />
      ) : isMobileRoute(window.location.pathname) ? (
        /* Phone-sized quick-check view (#364) — bypasses the desktop tab shell. */
        <MobileQuickCheck />
      ) : (
    <div className="fm-app flex flex-col" style={{ height: '100vh', background: 'var(--bg)' }}>
      <GlassFilters />
      {/* Nav bar */}
      <nav
        className="fm-top-nav flex items-stretch shrink-0 relative z-20"
        style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)', height: 44 }}
      >
        {/* Logo — a live pipeline hex meter; click to open Overview */}
        <button
          onClick={() => selectTab('overview')}
          className="fm-brand flex items-center gap-2 shrink-0 cursor-pointer bg-transparent border-none"
          style={{ padding: '0 20px 0 16px' }}
          title="Pipeline status, open Overview"
        >
          <LogoMark stageStates={selectedSessionId !== null ? status.states : undefined} />
          <span className="fm-brand-text text-sm font-semibold whitespace-nowrap" style={{ color: 'var(--text)', fontFamily: 'var(--font-display)', letterSpacing: '0.01em' }}>
            Telemetry Frame Mapper
          </span>
        </button>

        {/* Pipeline tabs — the always-visible spine */}
        <div className="fm-pipeline-nav flex flex-1 items-stretch min-w-0 overflow-x-auto tg-noscrollbar">
          {PIPELINE_TABS.map((tab) => {
            const active = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => selectTab(tab.id)}
                className="relative px-3 text-sm cursor-pointer border-none bg-transparent h-full flex items-center whitespace-nowrap"
                style={{
                  color: active ? 'var(--text)' : 'var(--text-muted)',
                  fontFamily: 'var(--font-display)',
                  transition: 'color var(--dur) var(--ease)',
                }}
              >
                <span className="relative" style={{ zIndex: 1 }}>{tab.label}</span>
                {active && (
                  <motion.div
                    layoutId="activeTabPill"
                    className="tg-glass"
                    style={{
                      position: 'absolute',
                      inset: '0 0',
                      borderRadius: 0,
                      zIndex: 0,
                      background: 'var(--splat-soft), color-mix(in srgb, var(--accent-soft) 55%, transparent)',
                      borderColor: 'transparent',
                      boxShadow: 'inset 0 -2px 0 var(--accent)',
                    }}
                    transition={{ duration: 0.3, ease: easeOut }}
                  />
                )}
              </button>
            )
          })}
        </div>

        {/* Tools — secondary tabs behind a dropdown (keeps the spine uncluttered) */}
        <div className="fm-tools-nav relative flex items-stretch shrink-0">
          <div aria-hidden="true" style={{ alignSelf: 'center', width: 1, height: 20, background: 'var(--border)', margin: '0 6px' }} />
          <button
            ref={toolsBtnRef}
            onClick={() => setToolsOpen((o) => !o)}
            onKeyDown={onToolsBtnKeyDown}
            aria-haspopup="menu"
            aria-expanded={toolsOpen}
            className="relative px-3 text-sm cursor-pointer border-none bg-transparent h-full flex items-center gap-1 whitespace-nowrap"
            style={{ color: toolActive ? 'var(--text)' : 'var(--text-muted)', fontFamily: 'var(--font-display)' }}
          >
            <span className="relative" style={{ zIndex: 1 }}>
              {toolActive ? TOOL_TABS.find((t) => t.id === activeTab)?.label : 'Tools'}
            </span>
            <span className="relative" style={{ zIndex: 1, fontSize: 10, opacity: 0.7 }}>▾</span>
            {toolActive && (
              <span
                aria-hidden="true"
                style={{ position: 'absolute', inset: 0, zIndex: 0, background: 'var(--splat-soft), color-mix(in srgb, var(--accent-soft) 55%, transparent)', boxShadow: 'inset 0 -2px 0 var(--accent)' }}
              />
            )}
          </button>
          {toolsOpen && (
            <>
              <div className="fixed inset-0" style={{ zIndex: 30 }} onClick={() => setToolsOpen(false)} />
              <div
                ref={menuRef}
                role="menu"
                onKeyDown={onMenuKeyDown}
                className="fm-tools-menu absolute"
                style={{ top: '100%', left: 6, zIndex: 31, minWidth: 168, background: 'var(--surface)', border: '1px solid var(--border-strong)', boxShadow: 'var(--shadow-2)', padding: 4 }}
              >
                {TOOL_TABS.map((tab) => {
                  const active = activeTab === tab.id
                  return (
                    <button
                      key={tab.id}
                      role="menuitem"
                      onClick={() => { selectTab(tab.id); setToolsOpen(false) }}
                      className="w-full text-left text-sm cursor-pointer border-none flex items-center"
                      style={{
                        padding: '7px 10px',
                        fontFamily: 'var(--font-display)',
                        color: active ? 'var(--accent-strong)' : 'var(--text)',
                        background: active ? 'var(--accent-soft)' : 'transparent',
                      }}
                      onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = 'var(--surface-2)' }}
                      onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = 'transparent' }}
                    >
                      {tab.label}
                    </button>
                  )
                })}
              </div>
            </>
          )}
        </div>

        {/* Project picker */}
        <div className="fm-project-slot flex items-center shrink-0" style={{ padding: '0 8px' }}>
          <ProjectPicker onCreateProject={() => {}} />
        </div>

        {/* Session picker */}
        <div className="fm-session-slot flex items-center shrink-0" style={{ padding: '0 8px', borderLeft: '1px solid var(--border)' }}>
          <SessionPicker projectId={selectedProjectId} onImport={() => setShowImport(true)} />
        </div>

        {/* Controls */}
        <div className="fm-import-slot flex items-center gap-2 shrink-0 pr-4">
          <button
            onClick={() => setShowImport(true)}
            className="text-sm cursor-pointer transition-colors duration-150 active:scale-[0.98]"
            style={{
              padding: '5px 14px',
              borderRadius: 'var(--edge)',
              background: 'var(--grad-splat)',
              color: 'var(--on-accent)',
              fontFamily: 'var(--font-display)',
              border: '1px solid var(--accent-hover)',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--grad-splat-hover)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--grad-splat)')}
          >
            + Import
          </button>
        </div>
      </nav>

      {/* Telemetry HUD — persistent pipeline status when a session is loaded */}
      {selectedSessionId !== null && (
        <StatusHud status={status} onGoToTab={(tab) => selectTab(tab as Tab)} />
      )}

      {/* Tab content */}
      <div className="flex flex-1 overflow-hidden">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={activeTab}
            className="flex flex-1 overflow-hidden"
            variants={reducedMotion ? reducedFade : splatBloom}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={reducedMotion ? { duration: 0.12 } : bloomTransition}
          >
            {renderTab(activeTab, () => setShowImport(true))}
          </motion.div>
        </AnimatePresence>
      </div>
      <ToastStack />
      <ImportModal open={showImport} onClose={() => setShowImport(false)} />
    </div>
      )}
    </>
  )
}
