import { useMapStore } from '../../shared/stores/mapStore'

const LAYERS = [
  { key: 'footprints' as const, label: 'Footprints', color: '#58a6ff' },
  { key: 'coverage' as const, label: 'Coverage', color: '#4ade80' },
  { key: 'heatmap' as const, label: 'Heatmap', color: '#f59e0b' },
  { key: 'targetArea' as const, label: 'Target Area', color: '#f59e0b' },
]

export default function LayerControls() {
  const { activeLayers, toggleLayer } = useMapStore()

  return (
    <div
      className="absolute top-3 left-3 z-[1000] rounded-lg"
      style={{
        background: 'rgba(13,17,23,0.92)',
        border: '1px solid var(--border)',
        padding: '10px 12px',
        minWidth: 140,
      }}
    >
      <div
        className="text-xs uppercase tracking-wide mb-2"
        style={{ color: 'var(--text-muted)', letterSpacing: '0.06em' }}
      >
        Layers
      </div>
      {LAYERS.map(({ key, label, color }) => (
        <label
          key={key}
          className="flex items-center gap-2 text-xs cursor-pointer mb-1.5"
          style={{ color: 'var(--text)' }}
        >
          <input
            type="checkbox"
            checked={activeLayers[key]}
            onChange={() => toggleLayer(key)}
            style={{ accentColor: color, width: 12, height: 12 }}
          />
          {label}
        </label>
      ))}
    </div>
  )
}
