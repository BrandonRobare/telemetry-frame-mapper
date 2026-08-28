import { useMapStore } from '../../shared/stores/mapStore'
import { glassBackdrop } from '../../shared/motion/glassSupport'

// Checkbox accent colors mirror the warm-light map layer colors.
const LAYERS = [
  { key: 'footprints' as const, label: 'Footprints', color: 'var(--accent)' },
  { key: 'coverage' as const, label: 'Coverage', color: 'var(--sage)' },
  { key: 'slope' as const, label: 'Slope', color: 'var(--danger-accent)' },
]

interface Props {
  slopeError?: string
}

export default function LayerControls({ slopeError }: Props) {
  const { activeLayers, slopeOpacity, setSlopeOpacity, toggleLayer } = useMapStore()

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
      {activeLayers.slope && (
        <>
          <label className="flex items-center gap-2 text-xs mt-2" style={{ color: 'var(--text)' }}>
            Opacity
            <input
              aria-label="Slope overlay opacity"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={slopeOpacity}
              onChange={(event) => setSlopeOpacity(Number(event.target.value))}
              className="flex-1"
            />
          </label>
          {slopeError && <p className="text-xs mt-2" style={{ color: 'var(--danger)', marginBottom: 0 }}>{slopeError}</p>}
        </>
      )}
    </div>
  )
}
