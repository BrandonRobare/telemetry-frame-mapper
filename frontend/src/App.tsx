import { useState } from 'react'
import { useMapStore } from './shared/stores/mapStore'
import MapTab from './features/map/MapTab'

type Tab = 'map' | 'gps-sync' | 'review' | 'plan' | 'export'

const TABS: { id: Tab; label: string }[] = [
  { id: 'map', label: 'Map' },
  { id: 'gps-sync', label: 'GPS Sync' },
  { id: 'review', label: 'Review' },
  { id: 'plan', label: 'Plan' },
  { id: 'export', label: 'Export' },
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
        {activeTab === 'gps-sync' && <ComingSoon label="GPS Sync" />}
        {activeTab === 'review' && <ComingSoon label="Review" />}
        {activeTab === 'plan' && <ComingSoon label="Plan" />}
        {activeTab === 'export' && <ComingSoon label="Export" />}
      </div>
    </div>
  )
}
