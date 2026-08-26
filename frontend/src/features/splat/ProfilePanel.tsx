import { useMemo } from 'react'
import type { ProfileSample } from './measurementMath'

// ---------------------------------------------------------------------------
// SVG elevation profile chart + CSV export.
// Renders inline SVG inside the sidebar. No external chart library needed.
// ---------------------------------------------------------------------------

interface ProfilePanelProps {
  samples: ProfileSample[]
  onClear: () => void
}

export default function ProfilePanel({ samples, onClear }: ProfilePanelProps) {
  const csvContent = useMemo(() => buildCsv(samples), [samples])

  if (samples.length === 0) return null

  // Build SVG data
  const elevations = samples.map((s) => s.elevation).filter((e): e is number => e !== null)
  const distances = samples.map((s) => s.distance_m)
  const maxDist = distances[distances.length - 1] || 1
  const minY = elevations.length > 0 ? Math.min(...elevations) : 0
  const maxY = elevations.length > 0 ? Math.max(...elevations) : 1
  const rangeY = maxY - minY || 1

  const svgWidth = 240
  const svgHeight = 140
  const pad = { top: 12, right: 12, bottom: 22, left: 46 }
  const plotW = svgWidth - pad.left - pad.right
  const plotH = svgHeight - pad.top - pad.bottom

  function toSvgX(d: number): number {
    return pad.left + (d / maxDist) * plotW
  }

  function toSvgY(y: number | null): number | null {
    if (y === null) return null
    return pad.top + plotH - ((y - minY) / rangeY) * plotH
  }

  const validPoints = samples
    .map((s) => ({ x: toSvgX(s.distance_m), y: toSvgY(s.elevation) }))
    .filter((p): p is { x: number; y: number } => p.y !== null)

  const polylinePoints = validPoints.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')

  // Axis ticks
  const yTickCount = 4
  const yTicks: { y: number; label: string }[] = []
  for (let i = 0; i <= yTickCount; i++) {
    const val = minY + (rangeY * i) / yTickCount
    yTicks.push({
      y: pad.top + plotH - (i / yTickCount) * plotH,
      label: val.toFixed(1),
    })
  }

  const xTickCount = 2
  const xTicks: { x: number; label: string }[] = []
  for (let i = 0; i <= xTickCount; i++) {
    const dist = (maxDist * i) / xTickCount
    xTicks.push({
      x: toSvgX(dist),
      label: dist >= 1000 ? `${(dist / 1000).toFixed(1)} km` : `${dist.toFixed(0)} m`,
    })
  }

  function triggerCsvDownload() {
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'elevation_profile.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  // SVG data URL export (browser-native, no external lib needed)
  function triggerSvgDownload() {
    const svgEl = document.getElementById('elevation-profile-svg')
    if (!svgEl) return
    const clone = svgEl.cloneNode(true) as SVGSVGElement
    // Inline styles so the exported SVG looks right standalone
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
    const serializer = new XMLSerializer()
    // The gridlines/axes/path all reference var(--border|text-muted|accent-strong|bg)
    // so the on-screen chart tracks theme changes live. CSS custom properties only
    // resolve against the document though, so once this clone is serialized and
    // detached it has nothing to resolve against and every stroke/fill silently
    // drops to none. Resolve each var(--x) to its current computed value — read
    // from the still-attached source, not the detached clone — before serializing.
    const svgString = inlineCssVariables(serializer.serializeToString(clone), svgEl)
    const dataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgString)
    const a = document.createElement('a')
    a.href = dataUrl
    a.download = 'elevation_profile.svg'
    a.click()
  }

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
          Elevation Profile
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

      <svg
        id="elevation-profile-svg"
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        style={{ width: '100%', height: 'auto', background: 'var(--bg)', borderRadius: 2 }}
      >
        {/* Grid lines */}
        {yTicks.map((t) => (
          <line
            key={`ygrid-${t.y}`}
            x1={pad.left} y1={t.y} x2={svgWidth - pad.right} y2={t.y}
            stroke="var(--border)" strokeWidth="0.5"
          />
        ))}
        {/* Y axis labels */}
        {yTicks.map((t) => (
          <text
            key={`ylabel-${t.y}`}
            x={pad.left - 3} y={t.y + 3}
            textAnchor="end"
            fill="var(--text-muted)"
            fontSize="7"
            fontFamily="monospace"
          >
            {t.label}
          </text>
        ))}
        {/* X axis labels */}
        {xTicks.map((t) => (
          <text
            key={`xlabel-${t.x}`}
            x={t.x} y={svgHeight - 2}
            textAnchor="middle"
            fill="var(--text-muted)"
            fontSize="7"
            fontFamily="monospace"
          >
            {t.label}
          </text>
        ))}
        {/* Profile polyline */}
        {polylinePoints && (
          <polyline
            points={polylinePoints}
            fill="none"
            stroke="var(--accent-strong)"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
        {/* Axis lines */}
        <line
          x1={pad.left} y1={pad.top} x2={pad.left} y2={pad.top + plotH}
          stroke="var(--text-muted)" strokeWidth="0.5"
        />
        <line
          x1={pad.left} y1={pad.top + plotH} x2={svgWidth - pad.right} y2={pad.top + plotH}
          stroke="var(--text-muted)" strokeWidth="0.5"
        />
      </svg>

      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>
          {samples.length} samples · {maxDist.toFixed(1)} m
        </span>
        <div style={{ display: 'flex', gap: 4 }}>
          <button
            onClick={triggerCsvDownload}
            style={{
              padding: '2px 6px', borderRadius: 2, fontSize: 9,
              border: '1px solid var(--border)', background: 'var(--surface-2)',
              color: 'var(--text)', cursor: 'pointer', fontFamily: 'inherit',
            }}
            title="Download CSV"
          >
            ↓ CSV
          </button>
          <button
            onClick={triggerSvgDownload}
            style={{
              padding: '2px 6px', borderRadius: 2, fontSize: 9,
              border: '1px solid var(--border)', background: 'var(--surface-2)',
              color: 'var(--text)', cursor: 'pointer', fontFamily: 'inherit',
            }}
            title="Download SVG chart"
          >
            ↓ SVG
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Resolve var(--token) references against a still-attached element's computed
// style so an exported/serialized copy renders standalone. Generic over the
// whole string (attributes and inline `style=` alike) so any current or future
// CSS variable used inside the chart is covered, not just the ones this file
// happens to name today.
// ---------------------------------------------------------------------------

function inlineCssVariables(svgString: string, source: Element): string {
  const computed = getComputedStyle(source)
  return svgString.replace(/var\((--[\w-]+)\)/g, (fullMatch, name: string) => {
    const value = computed.getPropertyValue(name).trim()
    return value || fullMatch
  })
}

// ---------------------------------------------------------------------------
// CSV builder
// ---------------------------------------------------------------------------

function buildCsv(samples: ProfileSample[]): string {
  const header = 'distance_m,x,z,elevation_m,lat,lon'
  const rows = samples.map((s) => {
    return [
      s.distance_m.toFixed(2),
      s.x.toFixed(3),
      s.z.toFixed(3),
      s.elevation !== null ? s.elevation.toFixed(3) : '',
      s.lat !== null ? s.lat.toFixed(7) : '',
      s.lon !== null ? s.lon.toFixed(7) : '',
    ].join(',')
  })
  return [header, ...rows].join('\n')
}