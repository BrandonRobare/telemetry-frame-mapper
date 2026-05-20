export interface FlightSettings {
  altitudeFt: number
  sideOverlapPct: number
  forwardOverlapPct: number
}

interface Props {
  settings: FlightSettings
  onChange: (next: FlightSettings) => void
  disabled?: boolean
}

interface SliderRowProps {
  label: string
  value: number
  min: number
  max: number
  step: number
  format: (v: number) => string
  onChange: (v: number) => void
  disabled?: boolean
}

function SliderRow({ label, value, min, max, step, format, onChange, disabled }: SliderRowProps) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="flex justify-between text-xs" style={{ color: 'var(--text-muted)', marginBottom: 6 }}>
        <span>{label}</span>
        <span style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{format(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: 'var(--accent)', cursor: disabled ? 'not-allowed' : 'pointer' }}
      />
    </div>
  )
}

export default function FlightSettingsPanel({ settings, onChange, disabled }: Props) {
  const set = (patch: Partial<FlightSettings>) => onChange({ ...settings, ...patch })

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase" style={{ color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 12 }}>
        Flight Settings
      </h3>
      <SliderRow
        label="Altitude"
        value={settings.altitudeFt}
        min={50} max={500} step={10}
        format={(v) => `${v} ft`}
        onChange={(v) => set({ altitudeFt: v })}
        disabled={disabled}
      />
      <SliderRow
        label="Side Overlap"
        value={settings.sideOverlapPct}
        min={50} max={90} step={5}
        format={(v) => `${v}%`}
        onChange={(v) => set({ sideOverlapPct: v })}
        disabled={disabled}
      />
      <SliderRow
        label="Forward Overlap"
        value={settings.forwardOverlapPct}
        min={50} max={90} step={5}
        format={(v) => `${v}%`}
        onChange={(v) => set({ forwardOverlapPct: v })}
        disabled={disabled}
      />
    </div>
  )
}
