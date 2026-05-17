import { useState } from 'react'
import { useMapStore } from './shared/stores/mapStore'
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
import { ToastStack } from './shared/components/ToastStack'
import ImportModal from './features/import/ImportModal'
import SessionPicker from './features/sessions/SessionPicker'

type Tab = 'map' | 'gps-sync' | 'review' | 'plan' | 'export' | 'session-log' | 'reconstruct' | 'jobs' | 'storage' | 'splat'

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
]

function ComingSoon({ label }: { label: string }) {
  return (
    <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
      <p>{label} — coming soon</p>
    </div>
  )
}

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('map')
  const [showImport, setShowImport] = useState(false)
  const { theme, toggleTheme } = useMapStore()

  return (
    <div className="flex flex-col" style={{ height: '100vh', background: 'var(--bg)' }}>
      {/* Nav bar */}
      <nav
        className="flex items-stretch shrink-0"
        style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)', height: 44 }}
      >
        {/* Logo */}
        <div className="flex items-center gap-2 shrink-0" style={{ padding: '0 20px 0 16px' }}>
          <div
            className="flex items-center justify-center rounded text-sm"
            style={{ width: 24, height: 24, background: 'linear-gradient(135deg, #58a6ff, #1f6feb)' }}
          >
            🛸
          </div>
          <span className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
            Frame Mapper
          </span>
        </div>

        {/* Tabs */}
        <div className="flex flex-1">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className="px-4 text-sm cursor-pointer border-none bg-transparent h-full"
              style={{
                color: activeTab === tab.id ? 'var(--accent)' : 'var(--text-muted)',
                borderBottom: activeTab === tab.id ? '2px solid var(--accent)' : '2px solid transparent',
                fontFamily: 'inherit',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Session picker */}
        <div className="flex items-center shrink-0" style={{ padding: '0 8px', borderLeft: '1px solid var(--border)' }}>
          <SessionPicker onImport={() => setShowImport(true)} />
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2 shrink-0 pr-4">
          <button
            onClick={toggleTheme}
            className="flex items-center gap-1.5 rounded-full text-xs cursor-pointer border"
            style={{
              padding: '4px 12px',
              background: 'transparent',
              borderColor: 'var(--border)',
              color: 'var(--text-muted)',
              fontFamily: 'inherit',
            }}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? '☾ Dark' : '☀ Light'}
          </button>
          <button
            onClick={() => setShowImport(true)}
            className="text-sm rounded cursor-pointer border-none"
            style={{
              padding: '5px 14px',
              background: 'var(--accent)',
              color: '#fff',
              fontFamily: 'inherit',
            }}
          >
            + Import
          </button>
        </div>
      </nav>

      {/* Tab content */}
      <div className="flex flex-1 overflow-hidden">
        {activeTab === 'map' && <MapTab />}
        {activeTab === 'gps-sync' && <GpsSyncTab />}
        {activeTab === 'review' && <ReviewTab />}
        {activeTab === 'plan' && <PlanTab />}
        {activeTab === 'export' && <ExportTab />}
        {activeTab === 'session-log' && <SessionLogTab />}
        {activeTab === 'reconstruct' && <ReconstructTab />}
        {activeTab === 'jobs' && <JobsTab />}
        {activeTab === 'storage' && <StorageTab />}
        {activeTab === 'splat' && <SplatViewerTab />}
      </div>
      <ToastStack />
      <ImportModal open={showImport} onClose={() => setShowImport(false)} />
    </div>
  )
}
