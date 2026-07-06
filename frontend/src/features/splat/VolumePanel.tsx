import { useMemo } from 'react'
import type { VolumeResult } from './measurementMath'

// ---------------------------------------------------------------------------
// Cut/fill volume results display with CSV export.
// ---------------------------------------------------------------------------

interface VolumePanelProps {
  volume: VolumeResult
  referenceElevation: number
  onClear: () => void
}

function fmtVol(v: number): string {
  if (Math.abs(v) < 0.01) return '0.00'
  if (Math.abs(v) >= 1000) return v.toFixed(0)
  return v.toFixed(2)
}

export default function VolumePanel({ volume, referenceElevation, onClear }: VolumePanelProps) {
  const csvContent = useMemo(
    () => buildVolumeCsv(volume, referenceElevation),
    [volume, referenceElevation],
  )

  function triggerCsvDownload() {
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'cut_fill_volume.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const netSign = volume.net_m3 > 0 ? '+' : volume.net_m3 < 0 ? '−' : ''
  const netLabel = volume.net_m3 > 0 ? 'Net Cut' : volume.net_m3 < 0 ? 'Net Fill' : 'Balanced'

  return (
    <div
      style={{
        marginTop: 8,
        padding: '8px 10px',
        borderRadius: 'var(--radius-sm)',
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--text)' }}>
          Cut / Fill Volume
        </span>
        <button
          onClick={onClear}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-muted)', fontSize: 10, padding: 0,
          }}
        >
          ✕ Clear
        </button>
      </div>

      <div style={{ fontSize: 9, color: 'var(--text-muted)', marginBottom: 2 }}>
        Reference elevation: {referenceElevation.toFixed(2)} m
        {volume.sampleCount > 0 && ` · ${volume.sampleCount} grid cells · ${volume.gridSpacingM.toFixed(2)} m spacing`}
      </div>

      {/* Results table */}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left', color: 'var(--text-muted)', fontWeight: 400, paddingBottom: 4 }}></th>
            <th style={{ textAlign: 'right', color: 'var(--text-muted)', fontWeight: 400, paddingBottom: 4 }}>m³</th>
            <th style={{ textAlign: 'right', color: 'var(--text-muted)', fontWeight: 400, paddingBottom: 4 }}>yd³</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style={{ color: '#4F6349', paddingBottom: 2 }}>Cut</td>
            <td style={{ textAlign: 'right', color: '#4F6349', fontVariantNumeric: 'tabular-nums' }}>
              {fmtVol(volume.cut_m3)}
            </td>
            <td style={{ textAlign: 'right', color: '#4F6349', fontVariantNumeric: 'tabular-nums' }}>
              {fmtVol(volume.cut_yd3)}
            </td>
          </tr>
          <tr>
            <td style={{ color: '#9A5E32', paddingBottom: 2 }}>Fill</td>
            <td style={{ textAlign: 'right', color: '#9A5E32', fontVariantNumeric: 'tabular-nums' }}>
              {fmtVol(volume.fill_m3)}
            </td>
            <td style={{ textAlign: 'right', color: '#9A5E32', fontVariantNumeric: 'tabular-nums' }}>
              {fmtVol(volume.fill_yd3)}
            </td>
          </tr>
          <tr style={{ borderTop: '1px solid var(--border)' }}>
            <td style={{ fontWeight: 600, color: 'var(--text)', paddingTop: 2 }}>
              {netLabel}
            </td>
            <td style={{ textAlign: 'right', fontWeight: 600, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>
              {netSign}{fmtVol(Math.abs(volume.net_m3))}
            </td>
            <td style={{ textAlign: 'right', fontWeight: 600, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>
              {netSign}{fmtVol(Math.abs(volume.net_yd3))}
            </td>
          </tr>
        </tbody>
      </table>

      <button
        onClick={triggerCsvDownload}
        style={{
          padding: '2px 6px', borderRadius: 2, fontSize: 9,
          border: '1px solid var(--border)', background: 'var(--surface-2)',
          color: 'var(--text)', cursor: 'pointer', fontFamily: 'inherit',
          alignSelf: 'flex-start',
        }}
        title="Download CSV"
      >
        ↓ Export CSV
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CSV builder
// ---------------------------------------------------------------------------

function buildVolumeCsv(volume: VolumeResult, referenceElevation: number): string {
  return [
    'metric,value_m3,value_yd3',
    `reference_elevation_m,${referenceElevation.toFixed(3)},`,
    `cut,${volume.cut_m3.toFixed(3)},${volume.cut_yd3.toFixed(3)}`,
    `fill,${volume.fill_m3.toFixed(3)},${volume.fill_yd3.toFixed(3)}`,
    `net,${volume.net_m3.toFixed(3)},${volume.net_yd3.toFixed(3)}`,
    `grid_spacing_m,${volume.gridSpacingM.toFixed(3)},`,
    `sample_count,${volume.sampleCount},`,
  ].join('\n')
}