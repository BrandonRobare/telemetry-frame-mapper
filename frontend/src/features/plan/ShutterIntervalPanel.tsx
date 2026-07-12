import { useState } from 'react'
import {
  CAMERA_PRESETS,
  DJI_MIN_INTERVAL_S,
  computeShutterInterval,
} from './shutterInterval'

interface Props {
  /** Live flight settings from the plan panel, so results stay in sync. */
  altitudeFt: number
  forwardOverlapPct: number
}

export default function ShutterIntervalPanel({ altitudeFt, forwardOverlapPct }: Props) {
  const [speedMs, setSpeedMs] = useState(5)
  const [presetIdx, setPresetIdx] = useState(0)

  const preset = CAMERA_PRESETS[presetIdx]
  const result = computeShutterInterval({
    speedMs,
    altitudeFt,
    forwardOverlapPct,
    fovVerticalDeg: preset.fovVerticalDeg,
  })

  return (
    <div style={{ marginTop: 20 }}>
      <h3
        className="text-xs font-semibold uppercase"
        style={{ color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 12 }}
      >
        Shutter Interval
      </h3>

      {/* Speed slider */}
      <div style={{ marginBottom: 12 }}>
        <div
          className="flex justify-between text-xs"
          style={{ color: 'var(--text-muted)', marginBottom: 6 }}
        >
          <span>Flight Speed</span>
          <span style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>
            {speedMs.toFixed(1)} m/s
          </span>
        </div>
        <input
          type="range"
          min={0.5}
          max={15}
          step={0.5}
          value={speedMs}
          onChange={(e) => setSpeedMs(Number(e.target.value))}
          style={{ width: '100%', accentColor: 'var(--accent)', cursor: 'pointer' }}
        />
      </div>

      {/* Camera preset */}
      <div style={{ marginBottom: 12 }}>
        <div className="text-xs" style={{ color: 'var(--text-muted)', marginBottom: 6 }}>
          Camera
        </div>
        <select
          className="text-xs"
          value={presetIdx}
          onChange={(e) => setPresetIdx(Number(e.target.value))}
          style={{
            width: '100%',
            padding: '4px 8px',
            border: '1px solid var(--border)',
            background: 'var(--surface-2)',
            color: 'var(--text)',
          }}
        >
          {CAMERA_PRESETS.map((p, i) => (
            <option key={p.name} value={i}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      {/* Results */}
      <div
        style={{
          padding: '10px 12px',
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
        }}
      >
        {result ? (
          <>
            {[
              ['Photo spacing', `${result.photoSpacingM.toFixed(1)} m`],
              ['Shutter interval', `${result.shutterIntervalS.toFixed(1)} s`],
              ['Forward footprint', `${result.footprintForwardM.toFixed(1)} m`],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between text-xs" style={{ marginBottom: 6 }}>
                <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                <span style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>
                  {value}
                </span>
              </div>
            ))}
            {result.belowDjiMinInterval && (
              <div className="text-xs" style={{ color: 'var(--warning, #d97706)', marginTop: 4 }}>
                Below the ~{DJI_MIN_INTERVAL_S} s DJI timed-shot minimum — slow down, fly
                higher, or reduce overlap.
              </div>
            )}
          </>
        ) : (
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
            Adjust speed, altitude, and overlap to see a recommendation.
          </div>
        )}
      </div>
    </div>
  )
}
