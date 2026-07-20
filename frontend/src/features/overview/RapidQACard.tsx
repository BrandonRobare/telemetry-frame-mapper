import type { QuickReport } from '../../types/api'

interface Props {
  report: QuickReport
  compact?: boolean
}

function statusBadge(safe: QuickReport['safe_to_reconstruct']): {
  label: string
  bg: string
  fg: string
  border: string
} {
  switch (safe) {
    case 'yes':
      return {
        label: 'Pass',
        bg: 'var(--success-soft)',
        fg: 'var(--success)',
        border: 'var(--success-accent)',
      }
    case 'caution':
      return {
        label: 'Caution',
        bg: 'var(--warning-soft)',
        fg: 'var(--warning)',
        border: 'var(--warning-accent)',
      }
    case 'no':
    default:
      return {
        label: 'Fail',
        bg: 'var(--danger-soft)',
        fg: 'var(--danger)',
        border: 'var(--danger-accent)',
      }
  }
}

export default function RapidQACard({ report, compact = false }: Props) {
  const badge = statusBadge(report.safe_to_reconstruct)
  const covStr =
    report.estimated_overlap_pct != null
      ? `${report.estimated_overlap_pct.toFixed(0)}%`
      : '—'

  return (
    <div
      className="fm-rapid-qa-card rounded"
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        padding: compact ? '10px 14px' : '14px 18px',
        borderRadius: 'var(--radius-md)',
      }}
    >
      <div
        className="flex items-baseline justify-between gap-3"
        style={{ marginBottom: compact ? 8 : 12 }}
      >
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 13, color: 'var(--text)' }}>
          Post-landing QA
        </div>
        <span
          className="text-xs rounded font-semibold"
          style={{
            background: badge.bg,
            color: badge.fg,
            border: `1px solid ${badge.border}`,
            padding: '1px 10px',
            borderRadius: 'var(--radius-sm)',
            fontFamily: 'var(--font-display)',
            fontSize: 12,
            lineHeight: '20px',
          }}
        >
          {badge.label} ({report.score})
        </span>
      </div>

      {/* Metrics row */}
      <div
        className="flex gap-3 flex-wrap"
        style={{ marginBottom: compact ? 6 : 10 }}
      >
        <Metric label="Frames" value={report.total_frames} />
        <Metric label="Usable" value={report.usable_frames} />
        <Metric label="GPS" value={`${report.gps_completeness_pct.toFixed(0)}%`} />
        <Metric label="Time" value={`${report.timestamp_completeness_pct.toFixed(0)}%`} />
        <Metric label="Blur" value={`${report.blur_pct.toFixed(0)}%`} />
        <Metric label="Exposure" value={`${report.exposure_issue_pct.toFixed(0)}%`} />
        {report.lighting_p10_p90_spread != null && (
          <Metric
            label="Lighting"
            value={report.lighting_inconsistent ? 'Variable' : 'Stable'}
            danger={report.lighting_inconsistent}
          />
        )}
        <Metric label="Overlap" value={covStr} />
        {report.match_density_avg_matches != null && (
          <Metric
            label="Matches"
            value={
              report.match_density_weak_ratio != null && report.match_density_weak_ratio >= 0.3
                ? 'Low'
                : `${report.match_density_avg_matches.toFixed(0)}`
            }
            danger={report.match_density_weak_ratio != null && report.match_density_weak_ratio >= 0.3}
          />
        )}
      </div>

      {/* Actionable warnings */}
      {report.warnings.length > 0 && (
        <div style={{ marginTop: compact ? 4 : 8 }}>
          {report.warnings.slice(0, compact ? 2 : undefined).map((w: string, i: number) => (
            <div
              key={i}
              className="text-xs"
              style={{
                color: 'var(--text-muted)',
                padding: '2px 0',
                lineHeight: 1.45,
              }}
            >
              ⚠ {w}
            </div>
          ))}
          {compact && report.warnings.length > 2 && (
            <div
              className="text-xs"
              style={{ color: 'var(--text-faint)', marginTop: 2 }}
            >
              +{report.warnings.length - 2} more
            </div>
          )}
        </div>
      )}

      {report.recommended_action && !compact && (
        <div
          className="text-xs"
          style={{
            marginTop: 8,
            padding: '6px 10px',
            background: 'var(--surface-2)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
            lineHeight: 1.45,
          }}
        >
          <span style={{ fontWeight: 600, color: 'var(--accent-strong)' }}>
            Recommended:{' '}
          </span>
          {report.recommended_action}
        </div>
      )}
    </div>
  )
}

function Metric({
  label,
  value,
  danger = false,
}: {
  label: string
  value: string | number
  danger?: boolean
}) {
  return (
    <div
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        padding: '3px 8px',
        background: 'var(--surface-2)',
        minWidth: 52,
        textAlign: 'center',
      }}
    >
      <div className="text-xs" style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-display)' }}>
        {label}
      </div>
      <div
        style={{
          color: danger ? 'var(--danger)' : 'var(--accent-strong)',
          fontFamily: 'var(--font-mono)',
          fontSize: 13,
          fontWeight: 600,
          lineHeight: '18px',
        }}
      >
        {value}
      </div>
    </div>
  )
}
