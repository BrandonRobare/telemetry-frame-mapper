import { useMapStore } from '../../shared/stores/mapStore'
import { glassBackdrop } from '../../shared/motion/glassSupport'

// Checkbox accent colors mirror the warm-light map layer colors.
const LAYERS = [
  { key: 'footprints' as const, label: 'Footprints', color: 'var(--accent)' },
  { key: 'coverage' as const, label: 'Coverage', color: 'var(--sage)' },
  { key: 'heatmap' as const, label: 'Heatmap', color: 'var(--warning-accent)' },
  { key: 'targetArea' as const, label: 'Target Area', color: 'var(--tan)' },
]

export default function LayerControls() {
  const { activeLayers, toggleLayer } = useMapStore()

  return (
    <div
      className="fm-layer-controls absolute top-3 left-3 z-[1000]"
      style={{
        background: 'color-mix(in srgb, var(--surface) 62%, transparent)',
        border: '1px solid var(--glass-border)',
        backdropFilter: glassBackdrop(true),
        WebkitBackdropFilter: 'blur(var(--glass-blur)) saturate(1.35)',
        boxShadow: 'var(--shadow-1)',
        padding: '10px 12px',
        minWidth: 140,
      }}
    >
      <div
        className="text-xs uppercase tracking-wide mb-2"
        style={{ color: 'var(--text-muted)', letterSpacing: '0.06em', fontFamily: 'var(--font-display)' }}
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
