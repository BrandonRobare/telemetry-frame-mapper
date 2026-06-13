import { useMapStore } from '../../shared/stores/mapStore'

// Checkbox accent colors mirror the warm-light map layer colors.
const LAYERS = [
  { key: 'footprints' as const, label: 'Footprints', color: '#B87C4C' },
  { key: 'coverage' as const, label: 'Coverage', color: '#A8BBA3' },
  { key: 'heatmap' as const, label: 'Heatmap', color: '#C8902F' },
  { key: 'targetArea' as const, label: 'Target Area', color: '#C4A484' },
]

export default function LayerControls() {
  const { activeLayers, toggleLayer } = useMapStore()

  return (
    <div
      className="absolute top-3 left-3 z-[1000] rounded-lg"
      style={{
        background: 'color-mix(in srgb, var(--surface) 92%, transparent)',
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
